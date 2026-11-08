"""Validate evidence integrity and coverage independently of parser selection."""
from pydantic import ValidationError

from .schemas import Issue, ParsedArticle, Validation
from .sentences import normalize

COVERAGE_THRESHOLD = 0.90


def validate(parsed: ParsedArticle, fallback_reason: str | None = None) -> Validation:
    counts = dict(blocks=0, headings=0, paragraphs=0, sentences=0, tables=0, images=0, ranked_entries=0)
    try:
        # Revalidate even model instances that have been mutated by a parser.
        parsed = ParsedArticle.model_validate(parsed.model_dump())
    except (ValidationError, AttributeError, TypeError) as exc:
        return Validation(status="error", warnings=[], errors=[Issue(code="SCHEMA_VALIDATION_FAILED", message=str(exc))], counts=counts)
    errors, warnings = [], list(parsed.warnings)
    seen = set()
    texts = []

    def error(code, message):
        errors.append(Issue(code=code, message=message))

    def check_id(value, expected):
        if value in seen or value != expected:
            error("INVALID_EVIDENCE_ID", f"Expected unique ID {expected}, got {value}")
        seen.add(value)

    def check_sentences(text, sentences, prefix):
        sentences = sentences or []
        if not text or normalize(text) != text or " ".join(s.text for s in sentences) != text:
            error("SENTENCE_INVARIANT_FAILED", f"Sentences do not reconstruct {prefix}")
        expected_start = 0
        for number, sentence in enumerate(sentences, 1):
            check_id(sentence.id, f"{prefix}.s{number}")
            if (sentence.start != expected_start or sentence.end != sentence.start + len(sentence.text)
                    or text[sentence.start:sentence.end] != sentence.text):
                error("SENTENCE_INVARIANT_FAILED", f"Invalid offsets in {sentence.id}")
            expected_start = sentence.end + 1
        counts["sentences"] += len(sentences)
        texts.append(text or "")

    for order, block in enumerate(parsed.blocks, 1):
        counts["blocks"] += 1
        check_id(block.id, f"block_{order:04d}")
        if block.order != order:
            error("INVALID_BLOCK_ORDER", f"Invalid order for {block.id}")
        counter = {"heading": "headings", "paragraph": "paragraphs", "table": "tables", "image": "images", "ranked_entry": "ranked_entries"}.get(block.type)
        if counter:
            counts[counter] += 1
        if block.type in {"paragraph", "list_item", "blockquote", "caption"}:
            check_sentences(block.text, block.sentences, block.id)
        elif block.type == "heading":
            texts.append(block.text or "")
            if block.sentences:
                error("SCHEMA_VALIDATION_FAILED", "Headings must be cited by block ID")
        elif block.type == "ranked_entry":
            for index, field in enumerate(block.fields or [], 1):
                if field.type == "paragraph":
                    counts["paragraphs"] += 1
                check_sentences(field.text, field.sentences, f"{block.id}.f{index}")
        elif block.type == "table":
            for row_number, row in enumerate(block.rows or [], 1):
                for col_number, cell in enumerate(row, 1):
                    check_id(cell.id, f"{block.id}.r{row_number}c{col_number}")
                    texts.append(cell.text)
    for block in parsed.blocks:
        if block.parent_id is not None:
            if block.parent_id not in seen:
                error("INVALID_EVIDENCE_ID", f"Unknown parent {block.parent_id}")
            if block.after_field is not None:
                parent = next((b for b in parsed.blocks if b.id == block.parent_id), None)
                if parent is None or parent.type != "ranked_entry" or block.after_field > len(parent.fields or []):
                    error("INVALID_BLOCK_ORDER", f"Invalid ranked image position for {block.id}")
    if not parsed.article.title or not parsed.article.title.strip():
        error("MISSING_TITLE", "Article title is missing")
    meaningful = any(b.type in {"paragraph", "list_item", "blockquote", "table", "ranked_entry"} for b in parsed.blocks)
    if not meaningful or not normalize(parsed.container_text):
        error("EXTRACTION_EMPTY", "No meaningful article body")
    source_words = len(parsed.container_text.split())
    extracted_words = len(" ".join(texts).split())
    if source_words and extracted_words < source_words * COVERAGE_THRESHOLD:
        error("TEXT_COVERAGE_LOW", f"Extracted {extracted_words}/{source_words} words, below {COVERAGE_THRESHOLD:.0%}")
    if counts["headings"] != parsed.container_heading_count:
        warnings.append(Issue(code="HEADING_COUNT_MISMATCH", message=f"Extracted {counts['headings']} of {parsed.container_heading_count} headings"))
    for field, code in [("author", "MISSING_AUTHOR"), ("published_at", "MISSING_DATE"), ("cover_image", "MISSING_COVER_IMAGE")]:
        if not getattr(parsed.article, field):
            warnings.append(Issue(code=code, message=f"Article {field} is missing"))
    if extracted_words < 100:
        warnings.append(Issue(code="SHORT_EXTRACTION", message=f"Only {extracted_words} words extracted"))
    if fallback_reason is not None:
        warnings.append(Issue(code="FALLBACK_USED", message=f"Human review required: {fallback_reason}"))
    return Validation(status="error" if errors else "warning" if warnings else "valid", warnings=warnings, errors=errors, counts=counts)
