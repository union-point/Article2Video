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


@pytest.mark.parametrize("verdict", ["supported", "unsupported"])
def test_script_names_numbers_and_attribution_defer_to_verifier(setup_pipeline, verdict):
    pipeline, provider = setup_pipeline
    prepare(pipeline)
    data = read_json(pipeline.path("script"))
    data["data"]["title"]["text"] = "Reading Searchbloom’s guide"
    scene = data["data"]["scenes"][0]
    scene["narration"][0]["text"] = "Only three companies publish prices in this ranking."
    scene["on_screen"][0]["text"] = "Acme has 100 locations"
    scene["title"]["text"] = "How the ranking works"
    write_json(pipeline.path("script"), data)
    provider.verdict = verdict
    _, report = pipeline.review("script", force=True)
    assert not report.errors
    assert not {"MISSING_NAME", "MISSING_VALUE", "RANKING_ATTRIBUTION"} & {f.code for f in report.flags}
    assert len(report.checks) == 1
    assert report.checks[0].verdict.status == verdict
    sent = [payload for name, payload, _ in provider.calls if name == "Verdict" and "approved_claims" in payload][-1]
    assert sent["candidate"] == data["data"]
    if verdict == "supported":
        assert not report.flags
        pipeline.auto_approve("script")
    else:
        assert {f.code for f in report.flags} == {"SEMANTIC_REVIEW"}
        with pytest.raises(ValueError, match="unsupported content"):
            pipeline.auto_approve("script")


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
    assert len([f for f in report.flags if f.code == "SEMANTIC_REVIEW"]) == 1
    assert all(check.verdict.status == "unsupported" for check in report.checks)
    with pytest.raises(ReviewRequired):
        pipeline.approve("script", "Reviewer")
