import pytest

from article_video.pipeline import Pipeline, ReviewRequired
from article_video.schemas import Facts
from article_video.storage import digest, read_json, write_json
from article_video.validation import validate_facts, validate_selection


def approve_selection(pipeline):
    pipeline.select()
    pipeline.approve("selection", "Test reviewer")


def approve_facts(pipeline):
    approve_selection(pipeline)
    pipeline.facts()
    pipeline.approve("facts", "Test reviewer")


def test_real_contract_indexes_nested_sentences_cells_and_nonoverlapping_sections(real_index):
    assert "block_0028.f3.s2" in real_index.evidence
    assert "block_0007.r2c2" in real_index.evidence
    assert "block_0028" not in real_index.evidence
    assert real_index.evidence["block_0028.f3.s2"].context["name"] == "Searchbloom"
    assert real_index.evidence["block_0007.r2c2"].context["table_row"]
    ids = [sid for s in real_index.sections.values() for sid in s.source_ids]
    assert len(ids) == len(set(ids)) == len(real_index.evidence)


def test_complete_offline_resume_approval_and_cache_flow(setup_pipeline):
    pipeline, provider = setup_pipeline
    with pytest.raises(ReviewRequired, match="Selection ready"):
        pipeline.run()
    assert [c[0] for c in provider.calls] == ["Selection"]
    pipeline.approve("selection", "Test reviewer")
    with pytest.raises(ReviewRequired, match="Facts ready"):
        pipeline.run()
    pipeline.approve("facts", "Test reviewer")
    with pytest.raises(ReviewRequired, match="Script ready"):
        pipeline.run()
    artifact, report = pipeline.review("script")
    assert not report.errors and not report.flags
    assert len(artifact.data.scenes) == 6
    assert len(report.checks) == 19
    assert all(c.run.resolved_model == pipeline.config.verifier_model for c in report.checks)
    pipeline.approve("script", "Test reviewer")
    count = len(provider.calls)
    assert pipeline.run().data == artifact.data
    assert len(provider.calls) == count
    assert "Acme reports" in (pipeline.output_dir / "script.md").read_text()
    # A model output is stable in content and provenance on a cache hit.
    assert digest(pipeline.script()) == digest(artifact)
    assert len(provider.calls) == count


def test_stage_commands_cannot_skip_checkpoints(setup_pipeline):
    pipeline, provider = setup_pipeline
    pipeline.select()
    with pytest.raises(ReviewRequired):
        pipeline.facts()
    pipeline.approve("selection", "Reviewer")
    pipeline.facts()
    with pytest.raises(ReviewRequired):
        pipeline.script()
    assert "Script" not in [c[0] for c in provider.calls]


def test_partial_verdict_is_reviewable_not_silently_approved(setup_pipeline):
    pipeline, provider = setup_pipeline
    approve_selection(pipeline)
    provider.verdict = "partial"
    pipeline.facts()
    _, report = pipeline.review("facts")
    assert len(report.flags) == 6
    with pytest.raises(ReviewRequired, match="Acknowledge"):
        pipeline.approve("facts", "Reviewer")
    pipeline.approve("facts", "Reviewer", "Reviewed the cited text and accepted these qualifications.",
                     [flag.id for flag in report.flags])
    assert pipeline._facts()[2]


def test_only_explicitly_approved_claims_are_sent_to_writer(setup_pipeline):
    pipeline, provider = setup_pipeline
    approve_selection(pipeline)
    pipeline.facts()
    pipeline.approve("facts", "Reviewer", claim_ids=["claim_001"])
    pipeline.script()
    sent = next(payload for name, payload, _ in provider.calls if name == "Script")
    assert [c["claim_id"] for c in sent["approved_claims"]] == ["claim_001"]


def test_unknown_and_out_of_selection_evidence_are_hard_errors(setup_pipeline):
    pipeline, _ = setup_pipeline
    approve_selection(pipeline)
    artifact = pipeline.facts()
    facts = artifact.data.model_copy(deep=True)
    facts.claims[0].source_ids = ["block_9999.s1"]
    with pytest.raises(ValueError, match="unknown evidence"):
        validate_facts(facts, pipeline.index, list(pipeline.index.sections))
    facts.claims[0].source_ids = ["block_0001"]
    with pytest.raises(ValueError, match="outside"):
        validate_facts(facts, pipeline.index, artifact.inputs.keys())


def test_missing_numbers_names_are_flags_and_uncited_context_is_not_evidence(setup_pipeline):
    pipeline, _ = setup_pipeline
    approve_selection(pipeline)
    pipeline.facts()
    path = pipeline.path("facts")
    payload = read_json(path)
    payload["data"]["claims"][0]["text"] = "FakeCorp scored 99 percent."
    write_json(path, payload)
    _, report = pipeline.review("facts")
    assert {"MISSING_VALUE", "MISSING_NAME"} <= {f.code for f in report.flags}
    with pytest.raises(ReviewRequired):
        pipeline.approve("facts", "Reviewer")


def test_edits_invalidate_approvals_and_downstream_inputs(setup_pipeline):
    pipeline, _ = setup_pipeline
    approve_facts(pipeline)
    payload = read_json(pipeline.path("facts"))
    payload["data"]["claims"][0]["text"] = payload["data"]["claims"][0]["text"].replace("its measurement", "the measurement")
    write_json(pipeline.path("facts"), payload)
    with pytest.raises(ReviewRequired, match="stale"):
        pipeline.script()
    pipeline.approve("facts", "Reviewer")
    pipeline.script()
    selection = read_json(pipeline.path("selection"))
    selection["data"]["angle"] = "Explain Acme's reporting."
    write_json(pipeline.path("selection"), selection)
    with pytest.raises(ReviewRequired, match="stale"):
        pipeline.review("script")


def test_force_bypasses_model_cache_and_normal_review_rechecks_tokens(setup_pipeline):
    pipeline, provider = setup_pipeline
    artifact = pipeline.select()
    count = len(provider.calls)
    assert pipeline.select() == artifact
    assert len(provider.calls) == count
    pipeline.select(force=True)
    assert len(provider.calls) == count + 1
    approve_selection(pipeline)
    pipeline.facts()
    pipeline.config.company_aliases["AbsentName"] = []
    with pytest.raises(ValueError, match="Stale"):
        pipeline.review("facts")


def test_bad_generation_does_not_replace_existing_output_or_enter_cache(setup_pipeline):
    pipeline, provider = setup_pipeline
    approve_selection(pipeline)
    pipeline.facts()
    original = pipeline.path("facts").read_bytes()
    cached = list((pipeline.runner.cache_dir / "facts").glob("*.json"))
    def corrupt(data):
        if isinstance(data, Facts):
            data.claims[0].source_ids = ["block_9999.s1"]
        return data
    provider.transform = corrupt
    with pytest.raises(ValueError, match="unknown evidence"):
        pipeline.facts(force=True)
    assert pipeline.path("facts").read_bytes() == original
    assert list((pipeline.runner.cache_dir / "facts").glob("*.json")) == cached


def test_selection_rejects_duplicates_and_noncontiguous_ranks(setup_pipeline):
    pipeline, _ = setup_pipeline
    data = pipeline.select().data.model_copy(deep=True)
    data.selected_section_ids[1] = data.selected_section_ids[0]
    with pytest.raises(ValueError, match="Duplicate"):
        validate_selection(data, pipeline.index)
    data.selected_section_ids = list(pipeline.index.sections)[:5]
    data.ranked_sections[0].rank = 99
    with pytest.raises(ValueError, match="ranks"):
        validate_selection(data, pipeline.index)


def test_article_edits_rejected_and_retrieval_time_is_not_content(setup_pipeline, article_path):
    pipeline, provider = setup_pipeline
    original_hash = pipeline.index.sha256
    document = read_json(article_path)
    document["source"]["retrieved_at"] = "2026-11-09T00:00:00Z"
    write_json(article_path, document)
    another = Pipeline(article_path, config=pipeline.config, provider=provider)
    assert another.index.sha256 == original_hash
    document["blocks"][2]["sentences"][0]["end"] += 1
    write_json(article_path, document)
    with pytest.raises(ValueError, match="Invalid frozen"):
        Pipeline(article_path, provider=provider)


def test_swapped_company_score_passes_recall_but_is_sent_to_independent_verifier(setup_pipeline, real_index):
    from types import SimpleNamespace
    from article_video.schemas import Artifact, Claim, PipelineConfig
    pipeline, provider = setup_pipeline
    run = pipeline.select().run
    pipeline.index = real_index
    pipeline.config = PipelineConfig()
    provider.verdict = "unsupported"
    claim = Claim(claim_id="claim_swapped", text="The SEO Works earned a score of 48 according to Searchbloom.",
                  source_ids=["block_0030", "block_0027", "block_0028.f3.s2"],
                  attribution="Searchbloom", company_names=["The SEO Works", "Searchbloom"])
    artifact = Artifact[Facts](stage="facts", inputs={}, run=run, data=Facts(claims=[claim]))
    selection = SimpleNamespace(data=SimpleNamespace(selected_section_ids=list(real_index.sections)))
    report = pipeline._facts_report(artifact, selection)
    assert not report.errors
    assert [f.code for f in report.flags] == ["SEMANTIC_REVIEW"]
    sent = provider.calls[-1][1]
    assert [s["id"] for s in sent["evidence"]] == claim.source_ids
    assert sent["candidate"]["text"] == claim.text
