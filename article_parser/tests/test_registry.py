import pytest

from article_parser import registry
from article_parser.exceptions import ExtractionError
from article_parser.parsers.searchbloom import SearchbloomParser
from article_parser.parsers.trafilatura_parser import TrafilaturaParser


@pytest.mark.parametrize("url,expected", [
    ("https://www.searchbloom.com/strategy/a-real-article", True),
    ("https://searchbloom.com/strategy/a-real-article/?x=1", True),
    ("https://SEARCHBLOOM.com/strategy/a-real-article", True),
    ("https://searchbloom.com/strategy/", False),
    ("https://searchbloom.com/strategy/page/2", False),
    ("https://searchbloom.com/strategy/archive", False),
    ("https://searchbloom.com/strategy/category/seo", False),
    ("https://searchbloom.com/strategy/2", False),
    ("https://searchbloom.com.evil.test/strategy/article", False),
    ("https://blog.searchbloom.com/strategy/article", False),
    ("https://searchbloom.com@evil.test/strategy/article", False),
    ("https://example.org/strategy/article", False),
    ("https://searchbloom.com/strategy/a%2Fb", False),
])
def test_matching(url, expected):
    assert SearchbloomParser().matches(url) is expected


class FailingParser:
    name, version = "forced-failure", "1"

    def matches(self, url):
        return True

    def parse(self, html, url):
        raise ExtractionError("TEMPLATE_MISMATCH", "Forced test failure")


def test_fallback(generic, monkeypatch):
    monkeypatch.setattr(registry, "SPECIALIZED_PARSERS", [FailingParser()])
    result = registry.extract_article(generic.html, generic.source)
    assert result.extraction.parser_name == "trafilatura"
    assert result.extraction.fallback_used
    assert "TEMPLATE_MISMATCH" in result.extraction.fallback_reason
    assert "FALLBACK_USED" in [w.code for w in result.validation.warnings]
    assert result.validation.status == "warning"


def test_validation_failure_falls_back(generic, parsed, monkeypatch):
    class InvalidParser(FailingParser):
        def parse(self, html, url):
            parsed.blocks = []
            return parsed
    monkeypatch.setattr(registry, "SPECIALIZED_PARSERS", [InvalidParser()])
    result = registry.extract_article(generic.html, generic.source)
    assert result.extraction.fallback_used
    assert "EXTRACTION_EMPTY" in result.extraction.fallback_reason


def test_both_fail(generic, monkeypatch):
    monkeypatch.setattr(registry, "SPECIALIZED_PARSERS", [FailingParser()])
    monkeypatch.setattr(TrafilaturaParser, "parse", FailingParser.parse)
    with pytest.raises(ExtractionError, match="FALLBACK_FAILED"):
        registry.extract_article(generic.html, generic.source)


def test_first_match_wins(monkeypatch):
    first, second = FailingParser(), FailingParser()
    monkeypatch.setattr(registry, "SPECIALIZED_PARSERS", [first, second])
    assert registry.select_parser("https://example.org") is first


def test_empty_input(generic):
    with pytest.raises(ExtractionError, match="EMPTY_HTML"):
        registry.extract_article("  ", generic.source)
