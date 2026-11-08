"""Repair flagged claims individually; never rewrite accepted content or approvals."""
from . import prompts
from .render import review_markdown
from .schemas import Claim, Facts
from .storage import digest, write_json, write_text
from .validation import validate_facts

REPAIR_PROMPT = prompts.SAFETY + """Repair ONLY this one flagged claim using the supplied
relevant evidence and review findings. Preserve claim_id. Correct wording and add
necessary exact citations; every name/quantity must occur in cited evidence.
Preserve qualifiers, attribution and entity/value relationships. Return one Claim,
not a replacement facts document. Do not remove claims or invent conclusions.
"""


def relevant_ids(index, claim, selected):
    """Cited prose/profile, table row+headers, and nearby headings; no whole article."""
    cited = set(claim.source_ids)
    blocks = {sid.split('.')[0] for sid in cited}
    result = set(cited)
    for sid in cited:
        evidence = index.evidence[sid]
        result.add(evidence.section_id)
        block = sid.split('.')[0]
        previous = f"block_{int(block.removeprefix('block_')) - 1:04d}"
        if previous in index.evidence:  # Only heading blocks themselves are evidence.
            result.add(previous)
        if '.r' in sid:
            row = sid.rsplit('c', 1)[0]
            result.update(s for s in index.evidence if s.startswith(row + 'c') or s.startswith(block + '.r1c'))
    for sid, evidence in index.evidence.items():
        if sid.split('.')[0] in blocks and '.r' not in sid:
            result.add(sid)
    return [sid for sid in index.evidence if sid in result and index.evidence[sid].section_id in selected]


def repair_facts(pipeline, claim_ids=(), extra_source_ids=()):
    selection, approval = pipeline._selection()
    inputs = {**pipeline.base_inputs(), 'selection': digest(selection), 'selection_approval': digest(approval)}
    artifact = pipeline.load('facts', inputs)
    selected = selection.data.selected_section_ids
    report = pipeline._facts_report(artifact, selection)
    if report.errors:
        raise ValueError('Structural errors must be corrected before targeted repair')
    flagged = {f.target for f in report.flags}
    requested = set(claim_ids) if claim_ids else flagged
    if not requested <= flagged:
        raise ValueError('Targeted repair accepts only currently flagged claim IDs')
    for sid in extra_source_ids:
        if sid not in pipeline.index.evidence or pipeline.index.evidence[sid].section_id not in selected:
            raise ValueError(f'Unknown or unselected repair evidence: {sid}')
    if not requested:
        return artifact, report  # Clean approved artifacts are a strict no-op.
    repaired = artifact.model_copy(deep=True)
    for pos, claim in enumerate(artifact.data.claims):
        if claim.claim_id not in requested:
            continue
        ids = list(dict.fromkeys([*relevant_ids(pipeline.index, claim, selected), *extra_source_ids]))
        payload = {'claim': claim.model_dump(), 'publisher': pipeline.config.publisher,
                   'findings': [f.model_dump() for f in report.flags if f.target == claim.claim_id],
                   'evidence': pipeline.index.records(ids)}
        def validate(candidate):
            if candidate.claim_id != claim.claim_id:
                raise ValueError('Repair must preserve claim_id')
            if not set(candidate.source_ids) <= set(ids):
                raise ValueError('Repair cited evidence outside its supplied scope')
            validate_facts(Facts(claims=[candidate]), pipeline.index, selected)
        candidate, info = pipeline.runner.run(
            'repair_facts', model=pipeline.config.verifier_model, version='targeted-repair.v1',
            prompt=REPAIR_PROMPT, payload=payload, schema=Claim, validate=validate, usage_stage="facts")
        repaired.data.claims[pos] = candidate
        # Per-claim provenance retains each independent model result.
        repaired.inputs[f'repair:{claim.claim_id}'] = digest(info)
        write_json(pipeline.output_dir / 'repairs' / f'{info.cache_key}.json',
                   {'claim_id': claim.claim_id, 'original_sha256': digest(claim), 'run': info.model_dump()})
    repaired.run = info
    repaired_report = pipeline._facts_report(repaired, selection)
    write_json(pipeline.output_dir / 'facts_repaired.json', repaired)
    write_json(pipeline.output_dir / 'facts_repaired_review.json', repaired_report)
    write_text(pipeline.output_dir / 'facts_repaired_review.md',
               review_markdown(repaired_report, repaired, pipeline.index))
    return repaired, repaired_report
