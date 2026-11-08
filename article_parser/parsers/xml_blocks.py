"""Convert Trafilatura's XML without claiming that it is the original DOM."""
from urllib.parse import urljoin

from lxml import etree

from ..schemas import Block, Cell, Issue, Link
from ..sentences import normalize, split_sentences

INLINE = {"hi", "ref", "del"}


def node_text(node):
    return normalize("".join(node.itertext()))


def xml_blocks(main, url: str):
    blocks, warnings = [], []
    headings = {}
    tree = main.getroottree()

    def links(node):
        return [Link(text=node_text(a), url=urljoin(url, a.get("target")))
                for a in node.iter("ref") if a.get("target")]

    def emit(kind, node, **kwargs):
        order = len(blocks) + 1
        block_id = f"block_{order:04d}"
        if kind in {"paragraph", "list_item", "blockquote", "caption"}:
            if not kwargs.get("text"):
                return
            kwargs["sentences"] = split_sentences(kwargs["text"], block_id)
        if kind == "table":
            for row_index, row in enumerate(kwargs["rows"], 1):
                for cell_index, cell in enumerate(row, 1):
                    cell.id = f"{block_id}.r{row_index}c{cell_index}"
        blocks.append(Block(id=block_id, type=kind, order=order,
                            section_path=[headings[k] for k in sorted(headings)],
                            source_kind="extracted_xml", source_locator=tree.getpath(node), **kwargs))

    def mixed(node, kind="paragraph", **kwargs):
        # Flush inline runs around structural children, avoiding duplicate nested text.
        parts, run_links = [node.text or ""], []
        def flush():
            text = normalize("".join(parts))
            if text:
                emit(kind, node, text=text, links=list(run_links), **kwargs)
            parts.clear()
            run_links.clear()
        for child in node:
            if child.tag in INLINE:
                parts.append("".join(child.itertext()))
                run_links.extend(links(child))
            else:
                flush()
                visit(child)
            parts.append(child.tail or "")
        flush()

    def visit(node):
        tag = node.tag
        if tag == "head":
            text = node_text(node)
            if not text:
                return
            rend = node.get("rend", "")
            if rend in {f"h{i}" for i in range(1, 7)}:
                level = int(rend[1:])
            else:
                level = 2
                warnings.append(Issue(code="HEADING_LEVEL_UNKNOWN", message="XML heading has no level; represented as level 2"))
            for key in list(headings):
                if key >= level:
                    del headings[key]
            headings[level] = text
            emit("heading", node, text=text, level=level, links=links(node))
        elif tag in {"p", "quote", "item", "caption"}:
            kind = {"p": "paragraph", "quote": "blockquote", "item": "list_item", "caption": "caption"}[tag]
            kwargs = {}
            if tag == "item":
                parents = [p for p in node.iterancestors() if p.tag == "list"]
                kwargs = {"list_depth": max(1, len(parents)), "list_ordered": bool(parents and parents[0].get("rend") == "ol")}
            mixed(node, kind, **kwargs)
        elif tag == "graphic":
            src = node.get("src")
            if src:
                emit("image", node, url=urljoin(url, src), alt=node.get("alt"))
            else:
                warnings.append(Issue(code="UNSUPPORTED_MEDIA", message="XML image has no source URL"))
        elif tag == "table":
            rows = []
            for row in node.findall("row"):
                cells = []
                for cell in row.findall("cell"):
                    cells.append(Cell(id="pending", text=node_text(cell), header=cell.get("role") == "head", links=links(cell)))
                    if any(cell.get(attr) for attr in ("span", "rowspan", "colspan")):
                        warnings.append(Issue(code="UNSUPPORTED_TABLE_SPAN", message="Table span cannot be represented"))
                if cells:
                    rows.append(cells)
            if rows:
                emit("table", node, rows=rows)
            else:
                warnings.append(Issue(code="UNSUPPORTED_TABLE", message="XML table has no rows"))
        elif tag in {"main", "div", "list"}:
            mixed(node)
        else:
            warnings.append(Issue(code="UNSUPPORTED_STRUCTURE", message=f"XML element {tag!r} represented as text"))
            mixed(node)

    visit(main)
    return blocks, warnings
