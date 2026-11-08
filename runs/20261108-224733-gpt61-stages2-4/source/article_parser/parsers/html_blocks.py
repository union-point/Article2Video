"""Original-DOM conversion for the inspected Searchbloom template."""
from urllib.parse import urljoin

from ..exceptions import ExtractionError
from ..schemas import Block, Cell, Issue, Link, TextField
from ..sentences import normalize, split_sentences

INLINE = {"a", "span", "strong", "em", "b", "i", "u", "small", "sup", "sub", "code", "s", "del", "mark", "abbr"}
BOUNDARIES = {"p", "div", "section", "li", "ul", "ol", "blockquote", "figure", "figcaption", "table", "tr", "td", "th", "caption", "br", "h1", "h2", "h3", "h4", "h5", "h6"}
JUNK_CLASSES = {"sb-preferred-source", "sb-ai-summarize", "sb-related"}


def visible_text(node):
    """Join inline text exactly; block/line boundaries become whitespace."""
    parts = [node.text or ""]
    for child in node:
        if isinstance(child.tag, str):
            separator = " " if child.tag in BOUNDARIES else ""
            parts.extend([separator, visible_text_raw(child), separator])
        parts.append(child.tail or "")
    return normalize("".join(parts))


def visible_text_raw(node):
    # Keep inline-edge whitespace until the complete block is normalized.
    parts = [node.text or ""]
    for child in node:
        if isinstance(child.tag, str):
            separator = " " if child.tag in BOUNDARIES else ""
            parts.extend([separator, visible_text_raw(child), separator])
        parts.append(child.tail or "")
    return "".join(parts)


def clean_container(body):
    for element in list(body.iter()):
        if not isinstance(element.tag, str) or element.getparent() is None:
            continue
        classes = set(element.get("class", "").split())
        if "sb-toc-label" in classes:
            sibling = element.getnext()
            if sibling is not None and sibling.tag in {"ul", "ol"}:
                sibling.drop_tree()
            element.drop_tree()
        elif element.tag in {"script", "style", "noscript"} or classes & JUNK_CLASSES:
            element.drop_tree()


class HTMLBlocks:
    def __init__(self, url, locators):
        self.url = url
        self.locators = locators
        self.blocks = []
        self.warnings = []
        self.headings = {}
        self.ranked = None

    def links(self, node):
        return [Link(text=visible_text(a), url=urljoin(self.url, a.get("href")))
                for a in node.iter("a") if a.get("href")]

    def emit(self, kind, node, **kwargs):
        order = len(self.blocks) + 1
        block_id = f"block_{order:04d}"
        if kind in {"paragraph", "list_item", "blockquote", "caption"}:
            if not kwargs.get("text"):
                return None
            if self.ranked is not None:
                field_id = f"{self.ranked.id}.f{len(self.ranked.fields) + 1}"
                # Keep labels inside source text too: offsets never refer to edited prose.
                strong = node.find("strong")
                label = visible_text(strong).rstrip(":") if strong is not None else None
                self.ranked.fields.append(TextField(
                    type=kind, label=label, source_locator=self.locators[node],
                    sentences=split_sentences(kwargs["text"], field_id), **kwargs))
                return None
            kwargs["sentences"] = split_sentences(kwargs["text"], block_id)
        if self.ranked is not None and kind == "image":
            kwargs.update(parent_id=self.ranked.id, after_field=len(self.ranked.fields))
        block = Block(id=block_id, type=kind, order=order,
                      section_path=[self.headings[k] for k in sorted(self.headings)],
                      source_kind="original_html", source_locator=self.locators[node], **kwargs)
        self.blocks.append(block)
        return block

    def start_ranked(self, node, rank, name):
        # Build only after collecting fields because the schema requires non-empty fields.
        order = len(self.blocks) + 1
        self.ranked = Block.model_construct(
            id=f"block_{order:04d}", type="ranked_entry", order=order,
            section_path=[self.headings[k] for k in sorted(self.headings)],
            source_kind="original_html", source_locator=self.locators[node],
            rank=rank, name=name, fields=[])
        self.blocks.append(self.ranked)

    def mixed(self, node, kind="paragraph", **kwargs):
        parts, links = [node.text or ""], []

        def flush():
            self.emit(kind, node, text=normalize("".join(parts)), links=list(links), **kwargs)
            parts.clear()
            links.clear()

        def inline(child):
            if child.tag == "img":
                flush()
                self.visit(child)
                return
            if child.tag == "br":
                parts.append(" ")
                return
            parts.append(child.text or "")
            if child.tag == "a" and child.get("href"):
                links.append(Link(text=visible_text(child), url=urljoin(self.url, child.get("href"))))
            for descendant in child:
                inline(descendant)
                parts.append(descendant.tail or "")

        for child in node:
            if not isinstance(child.tag, str):
                pass
            elif child.tag in INLINE or child.tag == "br":
                inline(child)
            else:
                flush()
                self.visit(child)
            parts.append(child.tail or "")
        flush()

    def visit(self, node):
        tag = node.tag
        if not isinstance(tag, str):
            return
        if tag in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            level = int(tag[1])
            text = visible_text(node)
            self.headings = {k: v for k, v in self.headings.items() if k < level}
            self.headings[level] = text
            self.emit("heading", node, text=text, level=level, links=self.links(node))
        elif tag == "img":
            src = node.get("data-lazy-src") or node.get("data-src") or node.get("src")
            if src:
                parent = node.getparent()
                links = self.links(parent) if parent is not None and parent.tag == "a" else []
                self.emit("image", node, url=urljoin(self.url, src), alt=node.get("alt"), links=links)
            else:
                self.warnings.append(Issue(code="UNSUPPORTED_MEDIA", message="Image has no source URL"))
        elif tag == "table":
            if self.ranked is not None:
                raise ExtractionError("TEMPLATE_MISMATCH", "Unexpected table inside ranked profile")
            rows = []
            block_id = f"block_{len(self.blocks) + 1:04d}"
            for row_index, row in enumerate(node.xpath('./tr|./thead/tr|./tbody/tr|./tfoot/tr'), 1):
                cells = []
                for cell_index, cell in enumerate(row.xpath('./th|./td'), 1):
                    if cell.get("rowspan", "1") != "1" or cell.get("colspan", "1") != "1":
                        raise ExtractionError("TEMPLATE_MISMATCH", "Table spans are not present in the verified template")
                    cells.append(Cell(id=f"{block_id}.r{row_index}c{cell_index}", text=visible_text(cell),
                                      header=cell.tag == "th", links=self.links(cell)))
                if cells:
                    rows.append(cells)
            table = self.emit("table", node, rows=rows)
            for caption in node.xpath('./caption'):
                self.visit(caption)
            for image in node.xpath('.//img'):
                self.visit(image)
                self.blocks[-1].parent_id = table.id
        elif tag == "blockquote":
            self.emit("blockquote", node, text=visible_text(node), links=self.links(node))
            for image in node.xpath('.//img'):
                self.visit(image)
        elif tag in {"p", "li", "figcaption", "caption"}:
            kind = {"p": "paragraph", "li": "list_item", "figcaption": "caption", "caption": "caption"}[tag]
            options = {}
            if tag == "li":
                parents = [p for p in node.iterancestors() if p.tag in {"ul", "ol"}]
                options = dict(list_depth=max(1, len(parents)), list_ordered=bool(parents and parents[0].tag == "ol"))
            self.mixed(node, kind, **options)
        elif tag in {"video", "audio", "iframe", "svg"}:
            self.warnings.append(Issue(code="UNSUPPORTED_MEDIA", message=f"Embedded {tag} at {self.locators[node]} requires review"))
        elif tag not in {"script", "style", "noscript"}:
            self.mixed(node)
