import pytest

from article_video.pipeline import ReviewRequired
from article_video.storage import read_json, write_json
from article_video.validation import validate_script


def prepare(pipeline):
    pipeline.select()
    pipeline.approve("selection", "Reviewer")
    pipeline.facts()
    pipeline.approve("facts", "Reviewer")
    return pipeline.script()


def test_script_numbers_and_names_checked_on_narration_titles_and_screen(setup_pipeline):
    pipeline, _ = setup_pipeline
    prepare(pipeline)
    data = read_json(pipeline.path("script"))
    scene = data["data"]["scenes"][0]
    scene["narration"][0]["text"] = "Acme scored 99 percent."
    scene["on_screen"][0]["text"] = "FakeCorp scored 100."
    scene["title"]["text"] = "Acme has 99 points"
    write_json(pipeline.path("script"), data)
    _, report = pipeline.review("script")
    targets = {f.target for f in report.flags if f.code == "MISSING_VALUE"}
    assert {"scene_001.title", "scene_001.narration.1", "scene_001.on_screen.1"} <= targets
    assert any(f.code == "MISSING_NAME" and f.target == "scene_001.on_screen.1" for f in report.flags)
    assert any(f.code == "RANKING_ATTRIBUTION" for f in report.flags)
    with pytest.raises(ReviewRequired):
        pipeline.approve("script", "Reviewer")


def test_unapproved_script_claims_and_multisentence_items_rejected(setup_pipeline):
    pipeline, _ = setup_pipeline
    artifact = prepare(pipeline)
    approved = pipeline._facts()[2]
    data = artifact.data.model_copy(deep=True)
    data.scenes[0].narration[0].claim_ids = ["claim_999"]
    data.scenes[0].claim_ids.append("claim_999")
    with pytest.raises(ValueError, match="unapproved"):
        validate_script(data, approved)
    data = artifact.data.model_copy(deep=True)
    data.scenes[0].narration[0].text += " Another sentence."
    with pytest.raises(ValueError, match="one sentence"):
        validate_script(data, approved)


def test_script_semantic_verifier_can_reject_novel_conclusions_even_without_new_tokens(setup_pipeline):
    pipeline, provider = setup_pipeline
    prepare(pipeline)
    provider.verdict = "unsupported"
    _, report = pipeline.review("script", force=True)
    assert len([f for f in report.flags if f.code == "SEMANTIC_REVIEW"]) == 19
    assert all(check.verdict.status == "unsupported" for check in report.checks)
    with pytest.raises(ReviewRequired):
        pipeline.approve("script", "Reviewer")
