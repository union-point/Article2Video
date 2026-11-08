import json
from pathlib import Path

from article_parser.__main__ import main
from article_parser.schemas import ArticleDocument

FIXTURE = Path(__file__).parent / "fixtures" / "generic_article.html"


def test_offline_cli(tmp_path, capsys):
    output = tmp_path / "article.json"
    assert main(["--html-file", str(FIXTURE), "--url", "https://example.org/orchard", "--output", str(output)]) == 0
    document = ArticleDocument.model_validate_json(output.read_text())
    assert document.validation.status == "warning"
    assert "WARNING UNSUPPORTED_STRUCTURES_REVIEW" in capsys.readouterr().out
    assert json.loads(output.read_text())["article"]["modified_at"] is None


def test_failure_does_not_overwrite(tmp_path, capsys):
    output = tmp_path / "article.json"
    output.write_text("previous artifact")
    assert main(["--html-file", str(tmp_path / "missing.html"), "--url", "https://example.org", "--output", str(output)]) == 1
    assert output.read_text() == "previous artifact"
    assert "FILE_ERROR" in capsys.readouterr().err
