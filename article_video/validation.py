"""Structural/reference checks; factual support and attribution use the LLM verifier."""
from article_parser.sentences import normalize, split_sentences

from .schemas import Review, ReviewItem
from .storage import digest

def add_issue(report, severity, code, target, message):
    item = ReviewItem(id=digest([code, target, message])[:16], code=code, target=target, message=message)
    getattr(report, severity).append(item)


def empty_review(stage, artifact):
    return Review(stage=stage, artifact_sha256=digest(artifact), errors=[], flags=[], checks=[])


def unique(values, description):
    if len(values) != len(set(values)):
        raise ValueError(f"Duplicate {description}")


def validate_selection(selection, index):
    known = set(index.sections)
    ranked = [s.section_id for s in selection.ranked_sections]
    unique(ranked, "ranked sections")
    if set(ranked) != known:
        raise ValueError(f"Selection must rank every catalogue section exactly once; missing={sorted(known-set(ranked))}, unknown={sorted(set(ranked)-known)}")
    if sorted(s.rank for s in selection.ranked_sections) != list(range(1, len(known) + 1)):
        raise ValueError("Section ranks must be contiguous and unique")
    selected = selection.selected_section_ids
    unique(selected, "selected sections")
    if not set(selected) <= known:
        raise ValueError("Selection contains unknown section IDs")
    if not 1 <= len(selected) <= min(7, len(known)):
        raise ValueError("Select 1–7 relevant sections")
    if len(split_sentences(normalize(selection.angle), "angle")) != 1:
        raise ValueError("The selection angle must be one sentence")


def validate_facts(facts, index, selected):
    unique([c.claim_id for c in facts.claims], "claim IDs")
    for claim in facts.claims:
        unique(claim.source_ids, f"citations in {claim.claim_id}")
        for source_id in claim.source_ids:
            if source_id not in index.evidence:
                raise ValueError(f"{claim.claim_id}: unknown evidence ID {source_id}")
            if index.evidence[source_id].section_id not in selected:
                raise ValueError(f"{claim.claim_id}: evidence {source_id} is outside the selected sections")


def script_items(script):
    yield "title", script.title
    for scene in script.scenes:
        yield f"{scene.scene_id}.title", scene.title
        for n, item in enumerate(scene.narration, 1):
            yield f"{scene.scene_id}.narration.{n}", item
        for n, item in enumerate(scene.on_screen, 1):
            yield f"{scene.scene_id}.on_screen.{n}", item


def validate_script(script, approved):
    unique([s.scene_id for s in script.scenes], "scene IDs")
    for scene in script.scenes:
        unique(scene.claim_ids, f"scene claim IDs in {scene.scene_id}")
        used = set().union(*(set(i.claim_ids) for i in [scene.title, *scene.narration, *scene.on_screen]))
        if used != set(scene.claim_ids):
            raise ValueError(f"{scene.scene_id}: claim_ids must exactly match all its text items")
        for item in scene.narration:
            if len(split_sentences(normalize(item.text), "narration")) != 1:
                raise ValueError(f"{scene.scene_id}: each narration item must contain exactly one sentence")
    for target, item in script_items(script):
        unique(item.claim_ids, f"claim references in {target}")
        if not set(item.claim_ids) <= set(approved):
            raise ValueError(f"{target}: unknown or unapproved claim IDs")


def facts_review(artifact, index, selected, config):
    report = empty_review("facts", artifact)
    try:
        validate_facts(artifact.data, index, selected)
    except ValueError as exc:
        add_issue(report, "errors", "INVALID_FACTS", "facts", str(exc))
        return report
    return report


def script_review(artifact, index, approved, config):
    report = empty_review("script", artifact)
    try:
        validate_script(artifact.data, approved)
    except ValueError as exc:
        add_issue(report, "errors", "INVALID_SCRIPT", "script", str(exc))
        return report
    return report
