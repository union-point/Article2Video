import pytest

from article_video.__main__ import main
from article_video.pipeline import ReviewRequired
from article_video.schemas import Approval, Facts, Selection
from article_video.storage import digest, read_json, write_json
from .test_cli import arguments


def test_auto_run_records_machine_approvals_and_resumes_idempotently(setup_pipeline):
    pipeline, provider = setup_pipeline
    result = pipeline.run(auto_approve=True)
    assert len(result.data.scenes) == 6
    receipts = {}
    for stage in ("selection", "facts", "script"):
        path = pipeline.output_dir / "approvals" / f"{stage}.json"
        receipts[stage] = path.read_bytes()
        receipt = read_json(path)
        assert receipt["mode"] == "automatic"
        assert receipt["reviewer"] == "article_video:auto-approve"
        assert receipt["accepted_review_items"] == []
    count = len(provider.calls)
    assert pipeline.run(auto_approve=True) == result
    assert len(provider.calls) == count
    for stage, original in receipts.items():
        assert (pipeline.output_dir / "approvals" / f"{stage}.json").read_bytes() == original


@pytest.mark.parametrize("verdict", ["partial", "unsupported"])
def test_auto_run_fails_when_no_supported_claims_remain(setup_pipeline, verdict):
    pipeline, provider = setup_pipeline
    provider.verdict = verdict
    with pytest.raises(ValueError, match="No fully supported claims"):
        pipeline.run(auto_approve=True)
    assert pipeline.path("facts").exists()
    assert not (pipeline.output_dir / "approvals/facts.json").exists()
    assert "Script" not in [c[0] for c in provider.calls]


def test_auto_approval_never_waives_invalid_evidence(setup_pipeline):
    pipeline, _ = setup_pipeline
    pipeline.run(auto_approve=True)
    payload = read_json(pipeline.path("facts"))
    payload["data"]["claims"][0]["source_ids"] = ["nonexistent"]
    write_json(pipeline.path("facts"), payload)
    previous = (pipeline.output_dir / "approvals/facts.json").read_bytes()
    with pytest.raises(ValueError, match="Cannot use structural"):
        pipeline.auto_approve("facts")
    assert (pipeline.output_dir / "approvals/facts.json").read_bytes() == previous


def test_auto_run_preserves_human_approval_and_explicit_claim_subset(setup_pipeline):
    pipeline, provider = setup_pipeline
    pipeline.select()
    pipeline.approve("selection", "Human reviewer")
    selection_receipt = (pipeline.output_dir / "approvals/selection.json").read_bytes()
    pipeline.facts()
    pipeline.approve("facts", "Human reviewer", claim_ids=["claim_001"])
    facts_receipt = (pipeline.output_dir / "approvals/facts.json").read_bytes()
    pipeline.run(auto_approve=True)
    assert (pipeline.output_dir / "approvals/selection.json").read_bytes() == selection_receipt
    assert (pipeline.output_dir / "approvals/facts.json").read_bytes() == facts_receipt
    sent = next(payload for name, payload, _ in provider.calls if name == "Script")
    assert [c["claim_id"] for c in sent["approved_claims"]] == ["claim_001"]


def test_auto_run_does_not_waive_unsupported_claims_from_human_receipts(setup_pipeline):
    pipeline, provider = setup_pipeline
    pipeline.select()
    pipeline.approve("selection", "Human reviewer")
    provider.verdict = "partial"
    pipeline.facts()
    _, report = pipeline.review("facts")
    pipeline.approve("facts", "Human reviewer", note="Reviewed the qualifications.", accepted=[f.id for f in report.flags])
    provider.verdict = "supported"
    before = (pipeline.output_dir / "approvals/facts.json").read_bytes()
    with pytest.raises(ValueError, match="No fully supported claims"):
        pipeline.run()
    assert (pipeline.output_dir / "approvals/facts.json").read_bytes() == before
    assert not pipeline.path("script").exists()


def test_auto_run_rebuilds_downstream_after_upstream_content_changes(setup_pipeline):
    pipeline, provider = setup_pipeline
    pipeline.run(auto_approve=True)
    old_facts = pipeline.path("facts").read_bytes()

    def change_angle(data):
        if isinstance(data, Selection):
            data.angle = "Explain Acme's review process."
        return data

    provider.transform = change_angle
    pipeline.run(force=True, auto_approve=True)
    assert pipeline.path("facts").read_bytes() != old_facts
    assert pipeline.run(auto_approve=True)


def test_legacy_human_receipt_hash_is_preserved(setup_pipeline):
    pipeline, _ = setup_pipeline
    pipeline.select()
    pipeline.approve("selection", "Human reviewer")
    raw = read_json(pipeline.output_dir / "approvals/selection.json")
    assert "mode" not in raw
    receipt = Approval.model_validate(raw)
    assert receipt.mode == "human"
    assert digest(receipt) == digest(raw)


def test_cli_review_mode_is_opt_in_and_auto_fails_when_nothing_is_supported(setup_pipeline, article_path, tmp_path, monkeypatch):
    pipeline, provider = setup_pipeline
    monkeypatch.setattr("article_video.llm.OpenAIProvider", lambda: provider)
    args = arguments(pipeline, article_path, tmp_path)
    assert main([*args, "run", "--mode", "review"]) == 2
    assert not (pipeline.output_dir / "approvals/selection.json").exists()
    assert main([*args, "select"]) == 0
    assert read_json(pipeline.output_dir / "approvals/selection.json")["mode"] == "automatic"
    provider.verdict = "partial"
    assert main([*args, "facts"]) == 1
    assert not (pipeline.output_dir / "approvals/facts.json").exists()
