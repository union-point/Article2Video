from pathlib import Path

from article_video.__main__ import main
from article_video.schemas import PipelineConfig
from article_video.storage import read_json, write_json


def arguments(pipeline, article_path, tmp_path):
    config = tmp_path / "config.json"
    write_json(config, pipeline.config)
    return ["--article", str(article_path), "--output-dir", str(pipeline.output_dir),
            "--cache-dir", str(pipeline.runner.cache_dir), "--config", str(config)]


def test_cli_runs_stages_stops_and_reports_exit_codes(setup_pipeline, article_path, tmp_path, monkeypatch, capsys):
    pipeline, provider = setup_pipeline
    monkeypatch.setattr("article_video.llm.OpenAIProvider", lambda: provider)
    args = [*arguments(pipeline, article_path, tmp_path), "--mode", "review"]
    assert main([*args, "run"]) == 2
    assert "REVIEW REQUIRED" in capsys.readouterr().out
    assert main([*args, "review", "selection"]) == 0
    assert main([*args, "approve", "selection", "--reviewer", "Reviewer"]) == 0
    assert main([*args, "facts"]) == 0
    assert main([*args, "approve", "facts", "--reviewer", "Reviewer"]) == 0
    assert main([*args, "script"]) == 0
    assert main([*args, "approve", "script", "--reviewer", "Reviewer"]) == 0
    assert main([*args, "review", "script"]) == 0


def test_cli_missing_key_and_malformed_config_fail_clearly(setup_pipeline, article_path, tmp_path, monkeypatch, capsys):
    pipeline, _ = setup_pipeline
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    args = arguments(pipeline, article_path, tmp_path)
    assert main([*args, "select"]) == 1
    assert "OPENAI_API_KEY" in capsys.readouterr().err
    config = Path(args[-1])
    config.write_text('{"unknown_field": true}')
    assert main([*args, "select"]) == 1
    assert "unknown_field" in capsys.readouterr().err


def test_exported_model_config_matches_implementation():
    root = Path(__file__).resolve().parents[2]
    config = PipelineConfig.model_validate(read_json(root / "configs" / "pipeline_config.json"))
    defaults = PipelineConfig()
    assert config.generation_model == defaults.generation_model
    assert config.verifier_model == defaults.verifier_model
