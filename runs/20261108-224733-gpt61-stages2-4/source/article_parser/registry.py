"""Ordered specialized parsers; fallback always receives the same HTML."""
from pydantic import ValidationError

from .exceptions import ExtractionError
from .parsers.base import ArticleParser
from .parsers.searchbloom import SearchbloomParser
from .parsers.trafilatura_parser import TrafilaturaParser
from .schemas import ArticleDocument, Extraction, ParsedArticle, Source
from .sentences import SPLITTER_NAME, SPLITTER_VERSION
from .validator import validate

SPECIALIZED_PARSERS: list[ArticleParser] = [SearchbloomParser()]


def select_parser(url: str) -> ArticleParser:
    return next((parser for parser in SPECIALIZED_PARSERS if parser.matches(url)), TrafilaturaParser())


def extract_article(html: str, source: Source) -> ArticleDocument:
    if not html.strip():
        raise ExtractionError("EMPTY_HTML", "The HTML body is empty")
    selected = select_parser(source.final_url)
    specialized = selected in SPECIALIZED_PARSERS
    attempts = [selected, TrafilaturaParser()] if specialized else [selected]
    reason = None
    for parser in attempts:
        try:
            parsed = ParsedArticle.model_validate(parser.parse(html, source.final_url))
            validation = validate(parsed, fallback_reason=reason)
            if validation.errors:
                raise ExtractionError("VALIDATION_FAILED", "; ".join(f"{e.code}: {e.message}" for e in validation.errors))
            return ArticleDocument(source=source, article=parsed.article, blocks=parsed.blocks,
                                   validation=validation, extraction=Extraction(
                                       parser_name=parser.name, parser_version=parser.version,
                                       splitter_name=SPLITTER_NAME, splitter_version=SPLITTER_VERSION,
                                       fallback_used=reason is not None, fallback_reason=reason))
        except Exception as exc:
            # Parser failures are isolated here; neither fetch nor file I/O occurs here.
            detail = f"{parser.name}: {exc}"
            if isinstance(exc, ValidationError):
                detail = f"SCHEMA_VALIDATION_FAILED: {detail}"
            if specialized and parser is selected:
                reason = detail
                continue
            if reason is not None:
                raise ExtractionError("FALLBACK_FAILED", f"{reason}; fallback: {detail}") from exc
            if isinstance(exc, ExtractionError):
                raise
            raise ExtractionError("PARSER_FAILURE", detail) from exc
    raise AssertionError("Unreachable parser state")
