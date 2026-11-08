from hashlib import sha256
from unittest.mock import Mock

import pytest
import requests

from article_parser import fetcher
from article_parser.exceptions import ExtractionError


def response(status=200, content=b"<html><p>Caf\xc3\xa9</p></html>", content_type="text/html; charset=utf-8"):
    return Mock(status_code=status, content=content, headers={"Content-Type": content_type}, url="https://example.org/final")


def test_fetch_preserves_bytes_and_redirect(tmp_path, monkeypatch):
    reply = response()
    get = Mock(return_value=reply)
    monkeypatch.setattr(fetcher.requests, "get", get)
    fetched = fetcher.fetch_html("https://example.org/start", tmp_path)
    digest = sha256(reply.content).hexdigest()
    assert (tmp_path / f"{digest}.html").read_bytes() == reply.content
    assert fetched.source.html_sha256 == digest
    assert fetched.source.requested_url.endswith("/start")
    assert fetched.source.final_url.endswith("/final")
    assert fetched.source.status == 200
    get.assert_called_once_with("https://example.org/start", timeout=(10, 30), allow_redirects=True)
    reply.close.assert_called_once()


@pytest.mark.parametrize("reply,code", [
    (response(status=404), "HTTP_ERROR"),
    (response(content_type="application/json"), "UNSUPPORTED_CONTENT_TYPE"),
    (response(content=b" \n"), "EMPTY_HTML"),
])
def test_reject_without_retry(reply, code, tmp_path, monkeypatch):
    get = Mock(return_value=reply)
    monkeypatch.setattr(fetcher.requests, "get", get)
    with pytest.raises(ExtractionError, match=code):
        fetcher.fetch_html("https://example.org", tmp_path)
    assert get.call_count == 1
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize("failure", [requests.Timeout(), response(status=429), response(status=503)])
def test_retry_then_success(failure, tmp_path, monkeypatch):
    get = Mock(side_effect=[failure, failure, response()])
    sleep = Mock()
    monkeypatch.setattr(fetcher.requests, "get", get)
    monkeypatch.setattr(fetcher.time, "sleep", sleep)
    assert fetcher.fetch_html("https://example.org", tmp_path).source.status == 200
    assert get.call_count == 3
    assert [c.args[0] for c in sleep.call_args_list] == [1, 2]


def test_timeout_exhausted(tmp_path, monkeypatch):
    get = Mock(side_effect=requests.Timeout())
    monkeypatch.setattr(fetcher.requests, "get", get)
    monkeypatch.setattr(fetcher.time, "sleep", Mock())
    with pytest.raises(ExtractionError, match="FETCH_TIMEOUT"):
        fetcher.fetch_html("https://example.org", tmp_path)
    assert get.call_count == 3


def test_load_is_offline(tmp_path, monkeypatch):
    get = Mock(side_effect=AssertionError("Offline mode used network"))
    monkeypatch.setattr(fetcher.requests, "get", get)
    path = tmp_path / "saved.html"
    data = b'<html><meta charset="utf-8"><p>Caf\xc3\xa9</p></html>'
    path.write_bytes(data)
    loaded = fetcher.load_html(path, "https://example.org")
    assert "Café" in loaded.html
    assert loaded.source.html_sha256 == sha256(data).hexdigest()
    assert loaded.source.status is None
    get.assert_not_called()
