"""Index the frozen parser contract without granting whole blocks citation status."""
from dataclasses import dataclass, field
from pathlib import Path

from article_parser.schemas import ArticleDocument, ParsedArticle
from article_parser.validator import validate

from .storage import digest, read_json


@dataclass
class Evidence:
    id: str
    text: str
    section_id: str
    headings: list[str]
    context: dict = field(default_factory=dict)


@dataclass
class Section:
    id: str
    title: str
    source_ids: list[str] = field(default_factory=list)


class EvidenceIndex:
    def __init__(self, document: ArticleDocument):
        if document.validation.status == "error" or document.validation.errors:
            raise ValueError("Article extraction has validation errors")
        # Recheck IDs, offsets and reconstruction; the original coverage source
        # is unavailable here, so this does not claim to revalidate extraction coverage.
        texts = []
        for block in document.blocks:
            if block.type == "ranked_entry":
                texts.extend(f.text for f in block.fields or [])
            elif block.type == "table":
                texts.extend(c.text for row in block.rows or [] for c in row)
            elif block.text:
                texts.append(block.text)
        result = validate(ParsedArticle(
            article=document.article, blocks=document.blocks, container_text=" ".join(texts),
            container_heading_count=sum(b.type == "heading" for b in document.blocks),
        ))
        if result.errors:
            raise ValueError("Invalid frozen article: " + "; ".join(e.message for e in result.errors))
        self.document = document
        content = document.model_dump(mode="json")
        content["source"].pop("retrieved_at", None)
        self.sha256 = digest(content)
        self.evidence: dict[str, Evidence] = {}
        self.sections: dict[str, Section] = {}
        self.company_names = {b.name for b in document.blocks if b.type == "ranked_entry" and b.name}
        # H2 sections contain their H3+ subsections; boundaries never overlap.
        levels = [b.level for b in document.blocks if b.type == "heading" and b.level > 1]
        boundary = min(levels) if levels else 1
        current = None
        for block in document.blocks:
            if current is None or (block.type == "heading" and block.level <= boundary):
                current = Section(block.id, block.text if block.type == "heading" else "Introduction")
                self.sections[current.id] = current

            def add(source_id, text, context=None):
                if source_id in self.evidence:
                    raise ValueError(f"Duplicate evidence ID: {source_id}")
                self.evidence[source_id] = Evidence(source_id, text, current.id, block.section_path, context or {})
                current.source_ids.append(source_id)

            if block.type == "heading":
                add(block.id, block.text)
            for sentence in block.sentences or []:
                add(sentence.id, sentence.text)
            for text_field in block.fields or []:
                for sentence in text_field.sentences:
                    add(sentence.id, sentence.text, {"name": block.name, "rank": block.rank, "label": text_field.label})
            for row in block.rows or []:
                context = {"table_headers": [c.text for c in block.rows[0]],
                           "table_row": [{"id": c.id, "text": c.text} for c in row]}
                for cell in row:
                    add(cell.id, cell.text, context)
        self.sections = {k: v for k, v in self.sections.items() if v.source_ids}

    @classmethod
    def load(cls, path: Path):
        return cls(ArticleDocument.model_validate(read_json(path)))

    def records(self, source_ids):
        return [vars(self.evidence[source_id]) for source_id in source_ids]

    def selection_input(self):
        return {"title": self.document.article.title,
                "sections": [{"section_id": s.id, "title": s.title, "evidence": self.records(s.source_ids)}
                             for s in self.sections.values()]}
