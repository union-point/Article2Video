from pathlib import Path

from lxml import html as lxml_html
import pytest

from article_parser.exceptions import ExtractionError
from article_parser.fetcher import load_html
from article_parser.parsers.html_blocks import visible_text
from article_parser.parsers.searchbloom import SearchbloomParser
from article_parser.registry import extract_article
from article_parser.validator import validate

FIXTURE = Path(__file__).parent / "fixtures" / "searchbloom_article.html"
URL = "https://www.searchbloom.com/strategy/best-ai-seo-agency-companies-services-usa"


@pytest.fixture(scope="module")
def source():
    return load_html(FIXTURE, URL)


@pytest.fixture
def searchbloom(source):
    return SearchbloomParser().parse(source.html, URL)


def all_text(parsed):
    texts = []
    for block in parsed.blocks:
        if block.text:
            texts.append(block.text)
        texts.extend(field.text for field in block.fields or [])
        for row in block.rows or []:
            texts.extend(cell.text for cell in row)
    return " ".join(texts)


def test_real_snapshot_and_metadata(searchbloom):
    assert searchbloom.article.title == "Best AI SEO Companies in 2026 (AEO and GEO)"
    assert searchbloom.article.author == "Cody C. Jensen"
    assert searchbloom.article.published_at == "2026-05-28T21:50:28+00:00"
    assert searchbloom.article.modified_at == "2026-10-29T22:51:29+00:00"
    assert searchbloom.article.language == "en-US"
    assert searchbloom.article.cover_image.startswith("https://www.searchbloom.com/wp-content/")
    assert validate(searchbloom).status == "valid"
    assert all_text(searchbloom) == searchbloom.container_text
    text = all_text(searchbloom)
    assert "Searchbloom publishes this guide and is one of the 9 companies ranked." in text
    assert "Writer's note: Hi, Cody C. Jensen here." in text
    assert "Refresh log. October 2026:" in text
    for junk in ["Summarize this article in:", "Add as a preferred source", "On this page", "Related Guides", '"@context"', ".sb-rank{"]:
        assert junk not in text


def test_headings_and_sections(searchbloom, source):
    root = lxml_html.fromstring(source.html)
    body = root.xpath('//div[contains(@class,"entry-content")]')[0]
    source_headings = [visible_text(h) for h in body.xpath('.//h2|.//h3')]
    headings = [b for b in searchbloom.blocks if b.type == "heading"]
    assert [b.text for b in headings[1:]] == source_headings
    assert len(headings) == 51
    ranked = next(b for b in searchbloom.blocks if b.type == "ranked_entry")
    assert ranked.section_path == [searchbloom.article.title, "The 9 Best AI SEO Companies", "1. Searchbloom"]
    note = next(b for b in searchbloom.blocks if b.text and b.text.startswith("Writer's note:"))
    assert note.section_path == [searchbloom.article.title, "A Note From the Author"]


def test_ranked_relationships_and_media(searchbloom):
    entries = [b for b in searchbloom.blocks if b.type == "ranked_entry"]
    assert [(b.rank, b.name) for b in entries] == list(enumerate([
        "Searchbloom", "The SEO Works", "Tinuiti", "Graphite", "iPullRank",
        "Single Grain", "Siege Media", "Seer Interactive", "Amsive"], 1))
    for entry in entries:
        labels = [f.label for f in entry.fields]
        assert labels[:5] == ["Summary", "Quick facts", "Scorecard", "Best for", "Overview"]
        assert labels[-2:] == ["Fees and terms", "Consider another pick if"]
        assert any(f.type == "list_item" and f.links for f in entry.fields)
    quote = next(f for f in entries[1].fields if f.type == "blockquote")
    assert '"Our content team writes clear, structured answers' in quote.text
    assert "In its own words, from" in quote.text
    assert quote.links[0].url.startswith("https://www.seoworks.co.uk/")
    images = [b for b in searchbloom.blocks if b.type == "image"]
    assert len(images) == 3  # No noscript duplicates or summary/preferred-source icons.
    assert all(b.url.startswith("https://www.searchbloom.com/wp-content/") for b in images)
    assert all(b.alt and b.links for b in images)
    image = next(b for b in images if b.parent_id)
    assert image.parent_id == entries[0].id
    assert image.after_field == 5  # Scorecard diagram follows Overview, before Published results.


def test_tables_are_exact(searchbloom, source):
    tables = [b for b in searchbloom.blocks if b.type == "table"]
    root = lxml_html.fromstring(source.html)
    original = root.xpath('//div[contains(@class,"entry-content")]//table')
    assert len(tables) == len(original) == 3
    for block, table in zip(tables, original):
        rows = table.xpath('./tr|./thead/tr|./tbody/tr|./tfoot/tr')
        assert [[c.text for c in row] for row in block.rows] == [
            [visible_text(c) for c in row.xpath('./th|./td')] for row in rows]
        assert all(c.header for c in block.rows[0])
        assert not any(c.header for row in block.rows[1:] for c in row)
        assert block.rows[1][0].id == f"{block.id}.r2c1"
        assert any(c.links for row in block.rows for c in row)


def test_evidence_ids_offsets_and_original_locators(searchbloom, source):
    root = lxml_html.fromstring(source.html)
    seen = set()
    for block in searchbloom.blocks:
        assert block.id not in seen
        seen.add(block.id)
        assert block.source_kind == "original_html"
        assert len(root.xpath(block.source_locator)) == 1
        units = ([block] if block.sentences else []) + (block.fields or [])
        for unit in units:
            assert " ".join(s.text for s in unit.sentences) == unit.text
            for sentence in unit.sentences:
                assert sentence.id not in seen
                seen.add(sentence.id)
                assert unit.text[sentence.start:sentence.end] == sentence.text
            # Ranked-field paths must point at the untouched DOM, despite removed widgets.
            if unit in (block.fields or []):
                assert visible_text(root.xpath(unit.source_locator)[0]) == unit.text
        for row in block.rows or []:
            for cell in row:
                assert cell.id not in seen
                seen.add(cell.id)


def test_determinism_and_no_fallback(source):
    first = extract_article(source.html, source.source)
    second_source = load_html(FIXTURE, URL)
    second = extract_article(second_source.html, second_source.source)
    left, right = first.model_dump(), second.model_dump()
    left["source"].pop("retrieved_at")
    right["source"].pop("retrieved_at")
    assert left == right
    assert not first.extraction.fallback_used
    assert first.extraction.parser_name == "searchbloom"


def test_original_coverage_failure(searchbloom):
    searchbloom.blocks = searchbloom.blocks[:10]
    assert "TEXT_COVERAGE_LOW" in {e.code for e in validate(searchbloom).errors}


def test_missing_container_is_never_body_fallback():
    with pytest.raises(ExtractionError, match="TEMPLATE_MISMATCH"):
        SearchbloomParser().parse("<html><body><h1>A title</h1><p>Text.</p></body></html>", URL)


def test_nested_lists_captions_inline_text_and_rank_not_inferred():
    html = '''<article class="article-holder"><h1 class="entry-title">Title</h1>
    <div class="entry-content card-text"><h2 id="profiles">Profiles</h2>
    <h3>Unranked company</h3><p class="sb-answer">Summary: No rank stated.</p>
    <p>Some <strong>exact</strong> punctuation, <a href="/link">here</a>.</p>
    <ul><li>Parent.<ul><li>Child.</li></ul>Tail.</li></ul>
    <figure><img data-src="/image.png" alt="View"><figcaption>A caption.</figcaption></figure>
    </div></article>'''
    parsed = SearchbloomParser().parse(html, URL)
    assert not any(b.type == "ranked_entry" for b in parsed.blocks)
    assert [b.text for b in parsed.blocks if b.type == "list_item"] == ["Parent.", "Child.", "Tail."]
    assert [b.list_depth for b in parsed.blocks if b.type == "list_item"] == [1, 2, 1]
    assert any(b.text == "Some exact punctuation, here." for b in parsed.blocks)
    assert next(b for b in parsed.blocks if b.type == "caption").sentences[0].text == "A caption."
    assert next(b for b in parsed.blocks if b.type == "image").url == "https://www.searchbloom.com/image.png"
