"""Read explicit metadata only: Article JSON-LD takes precedence over HTML."""
import json
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from ..schemas import Article
from ..sentences import normalize


def _objects(value):
    if isinstance(value, list):
        for item in value:
            yield from _objects(item)
    elif isinstance(value, dict):
        yield value
        for item in value.values():
            if isinstance(item, (dict, list)):
                yield from _objects(item)


def _value(value, keys=("name",)):
    if isinstance(value, str):
        return normalize(value) or None
    if isinstance(value, list):
        values = [_value(item, keys) for item in value]
        return ", ".join(v for v in values if v) or None
    if isinstance(value, dict):
        for key in keys:
            result = _value(value.get(key), keys)
            if result:
                return result
    return None


def read_metadata(html: str, url: str) -> Article:
    soup = BeautifulSoup(html, "lxml")
    data = {}
    for script in soup.select('script[type="application/ld+json"]'):
        try:
            objects = _objects(json.loads(script.string or script.get_text()))
            for obj in objects:
                types = obj.get("@type", [])
                if isinstance(types, str):
                    types = [types]
                if set(types) & {"Article", "BlogPosting", "NewsArticle"}:
                    data = obj
                    break
        except (ValueError, TypeError):
            continue
        if data:
            break

    def meta(*names):
        for name in names:
            tag = soup.find("meta", attrs={"property": name}) or soup.find("meta", attrs={"name": name})
            if tag and tag.get("content"):
                return normalize(tag["content"]) or None
        return None

    canonical = soup.find("link", rel="canonical")
    title_tag = soup.find("h1") or soup.find("title")
    canonical_url = (_value(data.get("mainEntityOfPage"), ("@id", "url"))
                     or _value(data.get("url"))
                     or (canonical.get("href") if canonical else None))
    cover = _value(data.get("image"), ("url", "contentUrl", "@id")) or meta("og:image", "twitter:image")
    return Article(
        title=_value(data.get("headline")) or meta("og:title", "twitter:title") or (normalize(title_tag.get_text()) if title_tag else None),
        author=_value(data.get("author")) or meta("author", "article:author"),
        published_at=_value(data.get("datePublished")) or meta("article:published_time", "date"),
        modified_at=_value(data.get("dateModified")) or meta("article:modified_time"),
        language=_value(data.get("inLanguage")) or meta("language", "og:locale") or (soup.html.get("lang") if soup.html else None),
        canonical_url=urljoin(url, canonical_url) if canonical_url else None,
        cover_image=urljoin(url, cover) if cover else None,
    )
