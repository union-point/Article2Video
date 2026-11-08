"""Searchbloom template verified against the saved October 2026 article."""
import re
from urllib.parse import unquote, urlsplit

from lxml import html as lxml_html

from ..exceptions import ExtractionError
from ..schemas import ParsedArticle
from .html_blocks import HTMLBlocks, clean_container, visible_text
from .metadata import read_metadata

ARTICLE_XPATH = '//article[contains(concat(" ", normalize-space(@class), " "), " article-holder ")]'
TITLE_XPATH = './/h1[contains(concat(" ", normalize-space(@class), " "), " entry-title ")]'
BODY_XPATH = './/div[contains(concat(" ", normalize-space(@class), " "), " entry-content ") and contains(concat(" ", normalize-space(@class), " "), " card-text ")]'


class SearchbloomParser:
    name = "searchbloom"
    version = "1.0.0"

    def matches(self, url: str) -> bool:
        try:
            parsed = urlsplit(url)
            parts = unquote(parsed.path).strip("/").split("/")
            return (parsed.scheme in {"http", "https"}
                    and parsed.hostname in {"searchbloom.com", "www.searchbloom.com"}
                    and len(parts) == 2 and parts[0] == "strategy"
                    and bool(parts[1]) and parts[1].lower() not in {
                        "page", "pages", "archive", "archives", "category", "tag", "feed",
                    } and not parts[1].isdigit())
        except ValueError:
            return False

    def parse(self, html: str, url: str) -> ParsedArticle:
        if not html.strip():
            raise ExtractionError("EMPTY_HTML", "The HTML body is empty")
        root = lxml_html.fromstring(html)
        articles = root.xpath(ARTICLE_XPATH)
        if len(articles) != 1:
            raise ExtractionError("TEMPLATE_MISMATCH", "Expected one article.article-holder")
        titles, bodies = articles[0].xpath(TITLE_XPATH), articles[0].xpath(BODY_XPATH)
        if len(titles) != 1 or len(bodies) != 1:
            raise ExtractionError("TEMPLATE_MISMATCH", "Missing or ambiguous entry title/content container")
        title, body = titles[0], bodies[0]
        # Capture paths before cleaning: removed siblings must not change provenance.
        tree = root.getroottree()
        locators = {element: tree.getpath(element) for element in root.iter() if isinstance(element.tag, str)}
        clean_container(body)
        builder = HTMLBlocks(url, locators)
        builder.visit(title)
        profiles = False
        children = list(body)
        for index, node in enumerate(children):
            if node.tag == "h2":
                profiles = node.get("id") == "profiles"
                builder.ranked = None
            if node.tag == "h3":
                builder.ranked = None
                match = re.fullmatch(r"(\d+)\.\s+(.+)", visible_text(node)) if profiles else None
                builder.visit(node)
                if match:
                    following = children[index + 1] if index + 1 < len(children) else None
                    if following is None or "sb-answer" not in following.get("class", "").split():
                        raise ExtractionError("TEMPLATE_MISMATCH", "Ranked profile is missing its summary")
                    builder.start_ranked(node, int(match[1]), match[2])
                continue
            builder.visit(node)
        return ParsedArticle(
            article=read_metadata(html, url), blocks=builder.blocks,
            warnings=builder.warnings,
            container_text=visible_text(title) + " " + visible_text(body),
            container_heading_count=1 + len(body.xpath('.//h1|.//h2|.//h3|.//h4|.//h5|.//h6')),
        )
