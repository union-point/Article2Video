"""Thin fallback extractor using the pinned Trafilatura 2.0.0 API."""
from bs4 import BeautifulSoup
from lxml import etree
import trafilatura

from ..exceptions import ExtractionError
from ..schemas import Issue, ParsedArticle
from .metadata import read_metadata
from .xml_blocks import xml_blocks


class TrafilaturaParser:
    name = "trafilatura"
    version = "2.0.0+adapter.1"

    def matches(self, url: str) -> bool:
        return True

    def parse(self, html: str, url: str) -> ParsedArticle:
        xml = trafilatura.extract(
            html, url=url, output_format="xml", include_tables=True,
            include_links=True, include_images=True, include_formatting=True,
            with_metadata=True, include_comments=False,
        )
        if not xml:
            raise ExtractionError("EXTRACTION_EMPTY", "Trafilatura returned no article")
        root = etree.fromstring(xml.encode(), parser=etree.XMLParser(resolve_entities=False, no_network=True))
        main = root.find("main")
        if main is None:
            raise ExtractionError("EXTRACTION_EMPTY", "Trafilatura XML has no main element")
        blocks, warnings = xml_blocks(main, url)
        # Do not treat Trafilatura's inferred dates/URLs as source metadata.
        metadata = read_metadata(html, url)
        soup = BeautifulSoup(html, "lxml")
        if soup.select("figcaption, caption, video, audio, iframe, td[rowspan], td[colspan], th[rowspan], th[colspan]"):
            warnings.append(Issue(code="UNSUPPORTED_STRUCTURES_REVIEW", message="Source has captions, embedded media, or table spans that Trafilatura may not preserve; compare with the snapshot"))
        return ParsedArticle(article=metadata, blocks=blocks, warnings=warnings,
                             container_text=" ".join(main.itertext()),
                             container_heading_count=len(main.findall(".//head")))
