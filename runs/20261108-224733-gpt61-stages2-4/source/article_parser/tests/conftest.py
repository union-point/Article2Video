from pathlib import Path

import pytest

from article_parser.fetcher import load_html
from article_parser.parsers.trafilatura_parser import TrafilaturaParser

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def generic():
    return load_html(FIXTURES / "generic_article.html", "https://example.org/orchard")


@pytest.fixture
def parsed(generic):
    return TrafilaturaParser().parse(generic.html, generic.source.final_url)
