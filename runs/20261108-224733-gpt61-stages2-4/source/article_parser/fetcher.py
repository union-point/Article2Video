"""Retrieve exact HTML bytes with bounded retries, or load an offline snapshot."""
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
import time

from bs4 import UnicodeDammit
import requests

from .exceptions import ExtractionError
from .schemas import Source


@dataclass(frozen=True)
class FetchedHTML:
    html: str
    source: Source


def _result(data: bytes, url: str, final_url: str, path: Path,
            status: int | None = None, content_type: str | None = None) -> FetchedHTML:
    if not data.strip():
        raise ExtractionError("EMPTY_HTML", "The HTML body is empty")
    decoded = UnicodeDammit(data, is_html=True).unicode_markup
    if decoded is None:
        raise ExtractionError("EMPTY_HTML", "Unable to decode HTML")
    return FetchedHTML(decoded, Source(
        requested_url=url, final_url=final_url,
        retrieved_at=datetime.now(timezone.utc).isoformat(),
        html_sha256=sha256(data).hexdigest(), snapshot_path=str(path),
        status=status, content_type=content_type,
    ))


def load_html(path: str | Path, url: str) -> FetchedHTML:
    path = Path(path)
    try:
        data = path.read_bytes()
    except OSError as exc:
        raise ExtractionError("FILE_ERROR", str(exc)) from exc
    return _result(data, url, url, path)


def fetch_html(url: str, snapshot_dir: str | Path = "snapshots") -> FetchedHTML:
    for attempt in range(3):
        try:
            response = requests.get(url, timeout=(10, 30), allow_redirects=True)
        except requests.Timeout as exc:
            if attempt < 2:
                time.sleep(2 ** attempt)
                continue
            raise ExtractionError("FETCH_TIMEOUT", "Request timed out after 3 attempts") from exc
        except requests.RequestException as exc:
            raise ExtractionError("HTTP_ERROR", str(exc)) from exc
        if (response.status_code == 429 or 500 <= response.status_code < 600) and attempt < 2:
            response.close()
            time.sleep(2 ** attempt)
            continue
        try:
            if response.status_code != 200:
                raise ExtractionError("HTTP_ERROR", f"HTTP {response.status_code} for {response.url}")
            content_type = response.headers.get("Content-Type", "")
            if content_type.split(";", 1)[0].strip().lower() not in {"text/html", "application/xhtml+xml"}:
                raise ExtractionError("UNSUPPORTED_CONTENT_TYPE", content_type or "Missing Content-Type")
            data = response.content
            path = Path(snapshot_dir) / f"{sha256(data).hexdigest()}.html"
            result = _result(data, url, response.url, path, response.status_code, content_type)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
            return result
        finally:
            response.close()
    raise AssertionError("Unreachable retry state")
