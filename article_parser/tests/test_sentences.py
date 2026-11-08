import pytest

from article_parser.sentences import normalize, split_sentences


@pytest.mark.parametrize("text,expected", [
    ("Acme Inc. works in the U.S. It scored 3.5 points.", ["Acme Inc. works in the U.S.", "It scored 3.5 points."]),
    ("Use examples, e.g. apples and pears. Then count.", ["Use examples, e.g. apples and pears.", "Then count."]),
    ("J. R. Smith arrived. We left.", ["J. R. Smith arrived.", "We left."]),
    ('She said “This works. Really well.” Then left.', ['She said “This works. Really well.”', 'Then left.']),
    ("A label without punctuation", ["A label without punctuation"]),
    ("", []),
])
def test_boundaries_and_offsets(text, expected):
    sentences = split_sentences(text, "block_0001")
    assert [s.text for s in sentences] == expected
    assert " ".join(s.text for s in sentences) == text
    for index, sentence in enumerate(sentences, 1):
        assert sentence.id == f"block_0001.s{index}"
        assert text[sentence.start:sentence.end] == sentence.text


def test_normalization_is_whitespace_only():
    assert normalize("  Exact\n wording —  3.5!\u00a0") == "Exact wording — 3.5!"
    with pytest.raises(ValueError):
        split_sentences("Unnormalized  text", "block_0001")


def test_all_fixture_sentences(parsed):
    ids = set()
    for block in parsed.blocks:
        assert block.id not in ids
        ids.add(block.id)
        if block.sentences:
            assert " ".join(s.text for s in block.sentences) == block.text
            for sentence in block.sentences:
                assert sentence.id not in ids
                ids.add(sentence.id)
                assert block.text[sentence.start:sentence.end] == sentence.text
        for row in block.rows or []:
            for cell in row:
                assert cell.id not in ids
                ids.add(cell.id)
