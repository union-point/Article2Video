from article_parser.validator import validate


def codes(parsed):
    return {error.code for error in validate(parsed).errors}


def test_valid(parsed):
    assert validate(parsed).status == "warning"  # Explicit caption-loss review warning.
    assert not validate(parsed).errors


def test_missing_title(parsed):
    parsed.article.title = None
    assert "MISSING_TITLE" in codes(parsed)


def test_coverage_loss(parsed):
    parsed.blocks = parsed.blocks[:3]
    assert "TEXT_COVERAGE_LOW" in codes(parsed)


def test_empty(parsed):
    parsed.blocks = []
    assert "EXTRACTION_EMPTY" in codes(parsed)


def test_bad_offsets(parsed):
    block = next(b for b in parsed.blocks if b.sentences)
    block.sentences[0].start += 1
    assert "SENTENCE_INVARIANT_FAILED" in codes(parsed)


def test_missing_sentences(parsed):
    block = next(b for b in parsed.blocks if b.sentences)
    block.sentences = []
    assert "SCHEMA_VALIDATION_FAILED" in codes(parsed)


def test_duplicate_id(parsed):
    parsed.blocks[1].id = parsed.blocks[0].id
    assert "INVALID_EVIDENCE_ID" in codes(parsed)


def test_schema_mutation(parsed):
    parsed.blocks[0].type = "invented"
    assert "SCHEMA_VALIDATION_FAILED" in codes(parsed)
