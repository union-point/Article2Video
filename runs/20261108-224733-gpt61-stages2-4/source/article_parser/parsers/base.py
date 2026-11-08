from typing import Protocol

from ..schemas import ParsedArticle


class ArticleParser(Protocol):
    name: str
    version: str

    def matches(self, url: str) -> bool: ...

    def parse(self, html: str, url: str) -> ParsedArticle: ...
