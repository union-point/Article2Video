from lxml import etree

from article_parser.parsers.metadata import read_metadata
from article_parser.parsers.xml_blocks import xml_blocks
from article_parser.registry import extract_article


def test_generic_structure(parsed):
    assert parsed.article.title == "Restoring the community orchard"
    assert parsed.article.author == "Mira Patel"
    assert parsed.article.published_at == "2026-03-12"
    assert parsed.article.cover_image == "https://example.org/orchard.jpg"
    assert all(b.source_kind == "extracted_xml" for b in parsed.blocks)
    assert all(b.source_locator.startswith("/doc/main/") for b in parsed.blocks)
    headings = [b for b in parsed.blocks if b.type == "heading"]
    assert [b.text for b in headings] == ["Restoring the community orchard", "A careful survey", "Work and observations", "What happens next"]
    assert headings[2].section_path == ["Restoring the community orchard", "Work and observations"]
    table = next(b for b in parsed.blocks if b.type == "table")
    assert [[c.text for c in row] for row in table.rows] == [["Area", "Trees planted"], ["East garden", "12"], ["West garden", "8"]]
    assert all(c.header for c in table.rows[0])
    assert table.rows[1][1].id == f"{table.id}.r2c2"
    assert any(link.url == "https://example.org/report" for b in parsed.blocks for link in b.links)
    assert next(b for b in parsed.blocks if b.type == "image").alt == "Apple trees beside a stone wall"
    text = " ".join(b.text or "" for b in parsed.blocks)
    assert "Editor's note:" in text
    assert "Copyright example organization" not in text
    assert "Home | Subscribe" not in text


def test_determinism(generic):
    first = extract_article(generic.html, generic.source).model_dump()
    second = extract_article(generic.html, generic.source).model_dump()
    assert first == second


def test_jsonld_precedes_meta_and_resolves_urls():
    metadata = read_metadata('''<html lang="en"><head>
    <meta name="author" content="Wrong Author">
    <script type="application/ld+json">{"@graph":[{"@type":"BlogPosting","headline":"Exact title","author":[{"name":"A"},{"name":"B"}],"image":{"url":"/cover.png"},"mainEntityOfPage":{"@id":"/canonical"},"dateModified":"2026-01-01"}]}</script>
    </head></html>''', "https://example.org/article")
    assert metadata.author == "A, B"
    assert metadata.title == "Exact title"
    assert metadata.cover_image == "https://example.org/cover.png"
    assert metadata.canonical_url == "https://example.org/canonical"
    assert metadata.modified_at == "2026-01-01"
    assert metadata.published_at is None


def test_nested_xml_and_inline_punctuation():
    main = etree.fromstring(b'''<main><head rend="h2">Topic</head><list rend="ol"><item>Parent <ref target="/a">link</ref>.<list rend="ul"><item>Child sentence.</item></list>Parent tail.</item></list><quote>A quote.</quote><caption>A caption.</caption></main>''')
    blocks, warnings = xml_blocks(main, "https://example.org")
    assert [b.text for b in blocks] == ["Topic", "Parent link.", "Child sentence.", "Parent tail.", "A quote.", "A caption."]
    assert [b.list_depth for b in blocks if b.type == "list_item"] == [1, 2, 1]
    assert blocks[1].links[0].url == "https://example.org/a"
    assert not warnings
