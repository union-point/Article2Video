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


def test_publisher_attribution_uses_metadata_without_unrelated_disclosure_claim(real_index):
    from article_video.schemas import Artifact, CitedText, Facts, PipelineConfig, Script
    from article_video.validation import script_review
    from pathlib import Path
    root = Path(__file__).resolve().parents[2]
    artifact = Artifact[Script].model_validate(read_json(root / "article_video/tests/fixtures/script_local_repair.json"))
    facts = Artifact[Facts].model_validate(read_json(root / "output/facts.json"))
    approved = {c.claim_id: c for c in facts.data.claims}
    item = CitedText(text="According to Searchbloom, AI SEO includes mostly traditional SEO work.",
                     claim_ids=["claim_004"], company_names=["Searchbloom"])
    artifact.data.scenes[1].narration[1] = item
    # Other items still use the disclosure, so the existing scene union is valid.
    report = script_review(artifact, real_index, approved, PipelineConfig())
    assert not [f for f in report.flags if f.target == "scene_002.narration.2"]
    # The source's role is established by approved attribution, not any arbitrary name.
    approved["claim_004"].attribution = "Another publisher"
    report = script_review(artifact, real_index, approved, PipelineConfig())
    assert any(f.code == "MISSING_NAME" and f.target == "scene_002.narration.2" for f in report.flags)


@pytest.mark.parametrize("text,allowed", [
    ("According to Searchbloom, AI SEO includes traditional SEO.", True),
    ("Searchbloom lists The SEO Works among the companies.", True),
    ("In Searchbloom's ranking, The SEO Works placed second.", True),
    ("Searchbloom ranked first.", False),
    ("Searchbloom ranks itself first.", False),
    ("Searchbloom says it ranks first.", False),
    ("According to Searchbloom, Searchbloom ranked first.", False),
])
def test_attribution_name_is_not_a_general_company_exemption(text, allowed):
    from article_video.validation import attribution_only
    assert attribution_only(text, "Searchbloom") is allowed


def test_attribution_metadata_does_not_authorize_numbers_or_other_names():
    from article_video.normalization import NameMatcher
    from article_video.schemas import Review
    from article_video.validation import token_checks
    report = Review(stage="script", artifact_sha256="x", errors=[], flags=[], checks=[])
    token_checks(report, "item", "According to Searchbloom, FakeCorp has 999 points.",
                 ["AI SEO uses traditional work."], NameMatcher([], {}),
                 attribution="Searchbloom")
    assert {f.code for f in report.flags} == {"MISSING_NAME", "MISSING_VALUE"}
    assert any("FakeCorp" in f.message for f in report.flags)
    assert not any("Searchbloom" in f.message for f in report.flags)


def test_publisher_alias_as_ranked_entity_still_needs_evidence():
    from article_video.normalization import NameMatcher
    from article_video.schemas import Review
    from article_video.validation import token_checks
    report = Review(stage="script", artifact_sha256="x", errors=[], flags=[], checks=[])
    token_checks(report, "item", "According to Searchbloom, Search Bloom ranked first.",
                 ["The SEO Works ranked first."],
                 NameMatcher([], {"Searchbloom": ["Search Bloom"]}), attribution="Searchbloom")
    assert any(f.code == "MISSING_NAME" for f in report.flags)
