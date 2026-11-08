"""Evidence schema and the internal parser result (no fetching or file writes)."""
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Issue(Model):
    code: str
    message: str


class Sentence(Model):
    id: str
    text: str
    start: int = Field(ge=0)
    end: int = Field(gt=0)


class Link(Model):
    text: str
    url: str


class Cell(Model):
    id: str
    text: str
    header: bool = False
    links: list[Link] = Field(default_factory=list)


class TextField(Model):
    type: Literal["paragraph", "list_item", "blockquote", "caption"] = "paragraph"
    source_locator: str | None = None
    list_depth: int | None = Field(default=None, ge=1)
    list_ordered: bool | None = None
    label: str | None = None
    text: str
    sentences: list[Sentence]
    links: list[Link] = Field(default_factory=list)


class Block(Model):
    id: str
    type: Literal["heading", "paragraph", "list_item", "blockquote", "caption", "image", "table", "ranked_entry"]
    order: int = Field(gt=0)
    section_path: list[str]
    source_kind: Literal["original_html", "extracted_xml"]
    source_locator: str = Field(min_length=1)
    text: str | None = None
    sentences: list[Sentence] | None = None
    links: list[Link] = Field(default_factory=list)
    level: int | None = Field(default=None, ge=1, le=6)
    list_depth: int | None = Field(default=None, ge=1)
    list_ordered: bool | None = None
    url: str | None = None
    alt: str | None = None
    rows: list[list[Cell]] | None = None
    rank: int | None = None
    name: str | None = None
    fields: list[TextField] | None = None
    parent_id: str | None = None
    after_field: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def required_content(self):
        if self.type in {"paragraph", "list_item", "blockquote", "caption"}:
            if not self.text or not self.sentences:
                raise ValueError("Text blocks require text and sentences")
        if self.type == "heading" and (not self.text or not self.level):
            raise ValueError("Headings require text and level")
        if self.type == "image" and not self.url:
            raise ValueError("Images require a URL")
        if self.type == "table" and not self.rows:
            raise ValueError("Tables require rows")
        if self.type == "ranked_entry" and (not self.name or not self.fields):
            raise ValueError("Ranked entries require a name and fields")
        return self


class Article(Model):
    title: str | None = None
    author: str | None = None
    published_at: str | None = None
    modified_at: str | None = None
    language: str | None = None
    canonical_url: str | None = None
    cover_image: str | None = None


class ParsedArticle(Model):
    article: Article
    blocks: list[Block]
    warnings: list[Issue] = Field(default_factory=list)
    # Coverage is measured against the cleaned source, never the emitted blocks.
    container_text: str
    container_heading_count: int = Field(ge=0)


class Source(Model):
    requested_url: str
    final_url: str
    retrieved_at: str
    html_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    snapshot_path: str
    status: int | None = None
    content_type: str | None = None


class Extraction(Model):
    parser_name: str
    parser_version: str
    splitter_name: str
    splitter_version: str
    fallback_used: bool
    fallback_reason: str | None = None


class Validation(Model):
    status: Literal["valid", "warning", "error"]
    warnings: list[Issue]
    errors: list[Issue]
    counts: dict[str, int]


class ArticleDocument(Model):
    schema_version: Literal["1.0"] = "1.0"
    source: Source
    extraction: Extraction
    article: Article
    blocks: list[Block]
    validation: Validation
