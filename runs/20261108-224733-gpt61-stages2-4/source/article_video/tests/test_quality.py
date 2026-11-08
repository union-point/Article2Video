from pathlib import Path

import pytest

from article_video.__main__ import main
from article_video.pipeline import ReviewRequired
from article_video.quality import CATEGORIES, script_quality_review
from article_video.render import script_markdown
from article_video.schemas import Artifact, PipelineConfig, Review, Script
from article_video.storage import digest, read_json, write_json
from article_video.validation import script_review
from .test_cli import arguments
from .test_script import prepare


FIXTURES = Path(__file__).resolve().parent / "fixtures"


def test_frozen_local_repair_regression_and_renderer_is_lossless(real_index):
    artifact = Artifact[Script].model_validate(read_json(FIXTURES / "script_local_repair.json"))
    original = artifact.model_dump()
    report = script_quality_review(artifact, real_index, PipelineConfig())
    assert report.categories == CATEGORIES
    assert report.artifact_sha256 == digest(artifact)
    codes = {f.code for f in report.flags}
    assert {"QUALITY_CAPITALIZATION", "QUALITY_REPETITION", "QUALITY_SCENE_TITLE",
            "QUALITY_VISUAL_SUITABILITY", "QUALITY_ON_SCREEN", "QUALITY_SCENE_COHERENCE"} <= codes
    caps = [f.message for f in report.flags if f.code == "QUALITY_CAPITALIZATION"]
    assert any("aI" in m for m in caps)
    assert any("tinuiti" in m for m in caps)
    assert not any("iPullRank'" in m.split("not ")[-1] for m in caps)
    assert artifact.model_dump() == original
    assert script_markdown(artifact) == (FIXTURES / "script_local_repair.md").read_text()


def test_quality_is_separate_stable_offline_and_never_repairs(setup_pipeline):
    p, provider = setup_pipeline
    artifact = prepare(p)
    before = {path: path.read_bytes() for path in p.output_dir.rglob("*") if path.is_file()}
    count = len(provider.calls)
    first = p.review_quality()
    assert not first.flags
    assert p.review_quality() == first
    assert len(provider.calls) == count
    assert all(path.read_bytes() == data for path, data in before.items())
    assert first.artifact_sha256 == digest(artifact)


@pytest.mark.parametrize("defect,code", [
    ("dense", "QUALITY_NATURALNESS"),
    ("capitalization", "QUALITY_CAPITALIZATION"),
    ("off_topic", "QUALITY_SCENE_COHERENCE"),
    ("visual", "QUALITY_VISUAL_SUITABILITY"),
    ("screen", "QUALITY_ON_SCREEN"),
    ("title", "QUALITY_SCENE_TITLE"),
    ("repeat", "QUALITY_REPETITION"),
])
def test_editorial_findings_block_auto_approval_without_regeneration(setup_pipeline, defect, code):
    p, provider = setup_pipeline
    artifact = prepare(p)
    scene = artifact.data.scenes[0]
    if defect == "dense":
        scene.narration[0].text = "Acme reports " + "the measurement process and " * 15 + "its limits."
    elif defect == "capitalization":
        scene.narration[0].text = scene.narration[0].text.replace("Acme", "acme")
    elif defect == "off_topic":
        scene.title.text = "Acme weather forecast"
    elif defect == "visual":
        scene.visual_direction = "Reveal the cited text in sequence."
    elif defect == "screen":
        scene.on_screen[0].text = "The " + "measurement " * 10 + "process"
    elif defect == "title":
        scene.title.text = "According to Acme, the process uses a baseline."
    else:
        scene.narration[0].text = artifact.data.scenes[1].narration[0].text
    write_json(p.path("script"), artifact)
    original = p.path("script").read_bytes()
    _, report = p.review("script")
    assert any(f.code == code for f in report.quality.flags)
    assert all(c.verdict.status == "supported" for c in report.checks)
    assert not any(f.code.startswith("QUALITY_") for f in script_review(artifact, p.index, p._facts()[2], p.config).flags)
    calls = len(provider.calls)
    with pytest.raises(ReviewRequired):
        p.auto_approve("script")
    assert len(provider.calls) == calls  # Reuse exact factual verdicts; quality is local.
    assert p.path("script").read_bytes() == original
    assert not (p.output_dir / "approvals/script.json").exists()
    p.approve("script", "Reviewer", note="Inspected these editorial findings.",
              accepted=[f.id for f in report.flags])
    assert p.approved_script()[0] == artifact


def test_new_quality_gate_invalidates_legacy_approval_without_new_model_calls(setup_pipeline):
    p, provider = setup_pipeline
    artifact = prepare(p)
    _, report = p.review("script")
    legacy = report.model_copy(deep=True)
    legacy.quality = None
    p._record_approval(artifact, legacy, "Legacy reviewer")
    receipt = (p.output_dir / "approvals/script.json").read_bytes()
    calls = len(provider.calls)
    with pytest.raises(ReviewRequired, match="stale"):
        p.approved_script()
    assert len(provider.calls) == calls
    assert (p.output_dir / "approvals/script.json").read_bytes() == receipt
    # The old schema does not add a null field to facts/selection hashes.
    assert "quality" not in Review(stage="facts", artifact_sha256="x", errors=[], flags=[], checks=[]).model_dump()


def test_review_quality_cli_needs_no_upstream_approval_or_api(setup_pipeline, article_path, tmp_path, monkeypatch):
    p, provider = setup_pipeline
    prepare(p)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    for path in (p.output_dir / "approvals").glob("*.json"):
        path.unlink()
    args = arguments(p, article_path, tmp_path)
    assert main([*args, "review-quality"]) == 0
    raw = read_json(p.path("script"))
    raw["data"]["scenes"][0]["visual_direction"] = "Reveal text."
    write_json(p.path("script"), raw)
    assert main([*args, "review-quality"]) == 2
    assert not list((p.output_dir / "approvals").glob("*.json"))


def test_source_acronyms_and_brand_casing_remain_intact(real_index):
    artifact = Artifact[Script].model_validate(read_json(FIXTURES / "script_local_repair.json"))
    scene = artifact.data.scenes[0]
    scene.narration[0].text = "iPullRank uses AI SEO and AEO."
    report = script_quality_review(artifact, real_index, PipelineConfig())
    assert not [f for f in report.flags if f.target == "scene_001.narration.1" and f.code == "QUALITY_CAPITALIZATION"]
    scene.narration[0].text = "ipullrank uses aI seo and aeo."
    report = script_quality_review(artifact, real_index, PipelineConfig())
    assert len([f for f in report.flags if f.target == "scene_001.narration.1" and f.code == "QUALITY_CAPITALIZATION"]) >= 4
