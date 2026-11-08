"""Resumable Stages 2–4, with content-bound human checkpoints."""
from datetime import datetime, timezone
from pathlib import Path

from pydantic import Field, create_model

from . import prompts
from .evidence import EvidenceIndex
from .llm import ModelRunner
from .quality import quality_markdown, script_quality_review
from .render import review_markdown, script_markdown
from .schemas import Approval, Artifact, Check, Facts, PipelineConfig, RankedSection, Script, Selection, Verdict
from .storage import digest, read_json, write_json, write_text
from .validation import (add_issue, empty_review, facts_review, script_items, script_review,
                         unique, validate_facts, validate_script, validate_selection)

MODELS = {"selection": Selection, "facts": Facts, "script": Script}
FILENAMES = {"selection": "selection.json", "facts": "facts.json", "script": "scenes.json"}


class ReviewRequired(ValueError):
    """Normal pipeline pause at a human checkpoint (CLI exit code 2)."""


class StaleArtifactError(ValueError):
    """Upstream content changed; automatic runs can regenerate this stage."""


class Pipeline:
    def __init__(self, article: Path, output_dir=Path("output"), cache_dir=Path("cache"),
                 config=None, provider=None):
        self.index = EvidenceIndex.load(article)
        self.output_dir = output_dir
        self.config = config or PipelineConfig()
        if self.config.min_narration_words > self.config.max_narration_words:
            raise ValueError("min_narration_words exceeds max_narration_words")
        self.runner = ModelRunner(cache_dir, provider, self.config.max_output_tokens)

    def path(self, stage):
        return self.output_dir / FILENAMES[stage]

    def base_inputs(self):
        return {"article": self.index.sha256, "config": digest(self.config)}

    def load(self, stage, inputs):
        artifact = Artifact[MODELS[stage]].model_validate(read_json(self.path(stage)))
        if artifact.stage != stage or artifact.inputs != inputs:
            raise StaleArtifactError(f"Stale {stage} artifact: input hashes changed; regenerate this stage")
        return artifact

    def _generate(self, stage, payload, inputs, validator, force):
        schema = MODELS[stage]
        if stage == "selection":
            count = len(self.index.sections)
            schema = create_model(
                "Selection", __base__=Selection,
                ranked_sections=(list[RankedSection], Field(min_length=count, max_length=count)),
                selected_section_ids=(list[str], Field(min_length=min(5, count), max_length=min(7, count))),
            )
        data, info = self.runner.run(
            stage, model=self.config.generation_model, version=prompts.VERSIONS[stage],
            prompt=getattr(prompts, stage.upper()), payload=payload, schema=schema,
            validate=validator, force=force,
        )
        # Dynamic response constraints must not leak distinct runtime subclasses
        # into otherwise identical artifacts on first generation versus cache hits.
        data = MODELS[stage].model_validate(data.model_dump())
        return Artifact[MODELS[stage]](stage=stage, inputs=inputs, run=info, data=data)

    def _save(self, artifact, report):
        # All API calls and checks finish before replacing previously valid outputs.
        write_json(self.path(artifact.stage), artifact)
        self._save_review(report, artifact)
        if artifact.stage == "script":
            write_text(self.output_dir / "script.md", script_markdown(artifact))

    def _save_review(self, report, artifact):
        write_json(self.output_dir / f"{report.stage}_review.json", report)
        write_text(self.output_dir / f"{report.stage}_review.md", review_markdown(report, artifact, self.index))
        if report.quality is not None:
            self._save_quality(report.quality)

    def _save_quality(self, report):
        write_json(self.output_dir / "script_quality_review.json", report)
        write_text(self.output_dir / "script_quality_review.md", quality_markdown(report))

    def review_quality(self):
        """Inspect even an unapproved draft offline; this cannot grant approval."""
        artifact = Artifact[Script].model_validate(read_json(self.path("script")))
        if artifact.stage != "script":
            raise ValueError("Expected a script artifact")
        report = script_quality_review(artifact, self.index, self.config)
        self._save_quality(report)
        return report

    def _verify(self, report, target, payload, force):
        verdict, info = self.runner.run(
            "verify", model=self.config.verifier_model, version=prompts.VERSIONS["verify"],
            prompt=prompts.VERIFY, payload=payload, schema=Verdict, validate=lambda value: None, force=force,
            usage_stage=report.stage,
        )
        # Store exact verifier model/prompt/cache provenance with each check.
        check = Check(target=target, text_sha256=digest(payload), verdict=verdict, run=info)
        report.checks.append(check)
        if verdict.status != "supported":
            add_issue(report, "flags", "SEMANTIC_REVIEW", target, f"{verdict.status}: {verdict.reason}")

    def _facts_report(self, artifact, selection, force=False):
        report = facts_review(artifact, self.index, selection.data.selected_section_ids, self.config)
        if not report.errors:
            for claim in artifact.data.claims:
                self._verify(report, claim.claim_id,
                             {"candidate": claim.model_dump(), "publisher": self.config.publisher,
                              "evidence": self.index.records(claim.source_ids)}, force)
        return report

    def _script_report(self, artifact, approved, force=False):
        report = script_review(artifact, self.index, approved, self.config)
        report.quality = script_quality_review(artifact, self.index, self.config)
        # Editorial findings use the same explicit acceptance/automatic-stop gate,
        # but never enter the factual verifier or trigger generation retries.
        report.flags.extend(report.quality.flags)
        if not report.errors:
            for target, item in script_items(artifact.data):
                claims = [approved[c] for c in item.claim_ids]
                source_ids = list(dict.fromkeys(s for c in claims for s in c.source_ids))
                self._verify(report, target,
                             {"candidate": item.model_dump(), "publisher": self.config.publisher,
                              "approved_claims": [c.model_dump() for c in claims],
                              "evidence": self.index.records(source_ids)}, force)
        return report

    def _selection_report(self, artifact):
        report = empty_review("selection", artifact)
        try:
            validate_selection(artifact.data, self.index)
        except ValueError as exc:
            add_issue(report, "errors", "INVALID_SELECTION", "selection", str(exc))
        for warning in self.index.document.validation.warnings:
            add_issue(report, "flags", warning.code, "article", warning.message)
        return report

    def _receipt(self, artifact, report):
        path = self.output_dir / "approvals" / f"{artifact.stage}.json"
        if not path.exists():
            raise ReviewRequired(f"Review {artifact.stage}_review.md and approve {artifact.stage} before continuing")
        receipt = Approval.model_validate(read_json(path))
        if (receipt.stage != artifact.stage or receipt.artifact_sha256 != digest(artifact)
                or receipt.review_sha256 != digest(report) or report.errors):
            raise ReviewRequired(f"{artifact.stage} approval is stale; review and approve the current artifact")
        if receipt.mode == "automatic" and (report.flags or receipt.accepted_review_items):
            raise ReviewRequired(f"{artifact.stage} automatic approval cannot accept review flags")
        required = self._relevant_flags(report, receipt.approved_claim_ids)
        if not required <= set(receipt.accepted_review_items):
            raise ReviewRequired(f"{artifact.stage} approval does not acknowledge current review flags")
        if artifact.stage == "facts":
            if not receipt.approved_claim_ids or not set(receipt.approved_claim_ids) <= {c.claim_id for c in artifact.data.claims}:
                raise ValueError("Invalid approved claim IDs in facts receipt")
        return receipt

    @staticmethod
    def _relevant_flags(report, claim_ids):
        return {f.id for f in report.flags if report.stage != "facts" or f.target in claim_ids or f.target == "facts"}

    def _selection(self):
        artifact = self.load("selection", self.base_inputs())
        report = self._selection_report(artifact)
        return artifact, self._receipt(artifact, report)

    def _facts(self):
        selection, selection_approval = self._selection()
        inputs = {**self.base_inputs(), "selection": digest(selection), "selection_approval": digest(selection_approval)}
        artifact = self.load("facts", inputs)
        report = self._facts_report(artifact, selection)
        receipt = self._receipt(artifact, report)
        approved = {c.claim_id: c for c in artifact.data.claims if c.claim_id in receipt.approved_claim_ids}
        return artifact, receipt, approved

    def approved_script(self):
        """Validate current approved content without rewriting any review artifacts."""
        facts, approval, approved = self._facts()
        artifact = self.load("script", {**self.base_inputs(), "facts": digest(facts), "facts_approval": digest(approval)})
        report = self._script_report(artifact, approved)
        return artifact, self._receipt(artifact, report)

    def select(self, force=False):
        artifact = self._generate("selection", {**self.index.selection_input(), "publisher": self.config.publisher},
                                  self.base_inputs(), lambda data: validate_selection(data, self.index), force)
        self._save(artifact, self._selection_report(artifact))
        return artifact

    def facts(self, force=False):
        selection, approval = self._selection()
        selected = selection.data.selected_section_ids
        source_ids = [sid for section in selected for sid in self.index.sections[section].source_ids]
        payload = {"angle": selection.data.angle, "publisher": self.config.publisher,
                   "selected_section_ids": selected, "evidence": self.index.records(source_ids)}
        inputs = {**self.base_inputs(), "selection": digest(selection), "selection_approval": digest(approval)}
        artifact = self._generate("facts", payload, inputs,
                                  lambda data: validate_facts(data, self.index, selected), force)
        self._save(artifact, self._facts_report(artifact, selection, force))
        return artifact

    def script(self, force=False):
        facts, approval, approved = self._facts()
        selection, _ = self._selection()
        payload = {"angle": selection.data.angle, "publisher": self.config.publisher,
                   "word_bounds": [self.config.min_narration_words, self.config.max_narration_words],
                   "approved_claims": [c.model_dump() for c in approved.values()]}
        inputs = {**self.base_inputs(), "facts": digest(facts), "facts_approval": digest(approval)}
        artifact = self._generate("script", payload, inputs, lambda data: validate_script(data, approved), force)
        self._save(artifact, self._script_report(artifact, approved, force))
        return artifact

    def review(self, stage, force=False):
        if stage == "selection":
            artifact = self.load(stage, self.base_inputs())
            report = self._selection_report(artifact)
        elif stage == "facts":
            selection, approval = self._selection()
            artifact = self.load(stage, {**self.base_inputs(), "selection": digest(selection), "selection_approval": digest(approval)})
            report = self._facts_report(artifact, selection, force)
        else:
            facts, approval, approved = self._facts()
            artifact = self.load(stage, {**self.base_inputs(), "facts": digest(facts), "facts_approval": digest(approval)})
            report = self._script_report(artifact, approved, force)
            write_text(self.output_dir / "script.md", script_markdown(artifact))
        self._save_review(report, artifact)
        return artifact, report

    def approve(self, stage, reviewer, note="", accepted=(), claim_ids=()):
        artifact, report = self.review(stage)
        return self._record_approval(artifact, report, reviewer, note, accepted, claim_ids)

    def _record_approval(self, artifact, report, reviewer, note="", accepted=(), claim_ids=(), mode="human"):
        stage = artifact.stage
        if report.errors:
            raise ValueError("Cannot approve structural/citation errors; edit the artifact and run review again")
        if mode == "automatic" and (report.flags or accepted):
            raise ReviewRequired(f"{stage} has {len(report.flags)} review flags; automatic approval requires a clean review. See {stage}_review.md")
        if stage == "facts":
            claim_ids = list(claim_ids) or [c.claim_id for c in artifact.data.claims]
            unique(claim_ids, "approved claim IDs")
            if not set(claim_ids) <= {c.claim_id for c in artifact.data.claims}:
                raise ValueError("Approval names an unknown claim ID")
        elif claim_ids:
            raise ValueError("--claim-id applies only to facts approval")
        required = self._relevant_flags(report, claim_ids)
        if set(accepted) - {f.id for f in report.flags}:
            raise ValueError("Unknown --accept-review-item ID")
        if required - set(accepted):
            raise ReviewRequired("Acknowledge each applicable review flag with --accept-review-item ID: " + ", ".join(sorted(required - set(accepted))))
        if required and not note.strip():
            raise ValueError("--note is required when accepting review flags")
        receipt = Approval(mode=mode, stage=stage, artifact_sha256=digest(artifact), review_sha256=digest(report),
                           reviewer=reviewer, note=note, reviewed_at=datetime.now(timezone.utc).isoformat(),
                           accepted_review_items=sorted(accepted), approved_claim_ids=list(claim_ids))
        write_json(self.output_dir / "approvals" / f"{stage}.json", receipt)
        return receipt

    def auto_approve(self, stage):
        """Preserve valid approvals; otherwise approve only a completely clean review."""
        artifact, report = self.review(stage)
        try:
            return self._receipt(artifact, report)
        except ReviewRequired:
            pass
        return self._record_approval(
            artifact, report, reviewer="article_video:auto-approve", mode="automatic",
            note="Opt-in automatic approval: no structural errors, no review flags, and all required semantic checks supported.",
        )

    def run(self, force=False, auto_approve=False):
        """Resume at checkpoints, optionally recording machine approvals of clean stages."""
        checkpoints = {
            "selection": "Selection ready; review selection_review.md and approve selection",
            "facts": "Facts ready; review facts_review.md and approve facts",
            "script": "Script ready; review script.md and script_review.md, then approve script",
        }
        for stage in MODELS:
            action = self.select if stage == "selection" else getattr(self, stage)
            generated = (force and stage == "selection") or not self.path(stage).exists()
            if generated:
                action(force)
                if not auto_approve:
                    raise ReviewRequired(checkpoints[stage])
            if auto_approve:
                try:
                    self.auto_approve(stage)
                except StaleArtifactError:
                    # A renewed upstream approval invalidates downstream inputs.
                    # Rebuild those artifacts, then apply the same clean-review gate.
                    action(force)
                    self.auto_approve(stage)
            else:
                artifact, report = self.review(stage)
                self._receipt(artifact, report)
        return artifact if not auto_approve else self.review("script")[0]
