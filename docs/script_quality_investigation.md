# Script pipeline investigation — 2026-11-08

This investigation describes the original local-repair artifact. That artifact
and its reviews were subsequently preserved in
[`before/`](../output/script_comparisons/20261108-213650/before/script.md).
The user then requested one generation with `script.v2`; see the
[before/after comparison](../output/script_comparisons/20261108-213650/comparison.md)
for the new draft and review results. References to the current script below
describe the state at the time of this investigation.

The current script is factually supported but editorially unsuitable. Its 26
cached factual verdicts are all `supported`; the separate offline quality review
finds 34 flags. These are heuristic findings, not 34 independently proven defects.
The former automatic approval is stale under the new review contract.

## Evidence and provenance

- Frozen source: `output/article.json`.
- Approved claim data: `output/facts.json`, 17 claims, `repair.v1` provenance.
- Current script: `output/scenes.json`, `requested_model: local-edit`,
  `prompt_version: script.repair.v1`, no response ID or token usage.
- Readable output: `output/script.md` exactly matches `script_markdown(artifact)`;
  the renderer does not change
  capitalization, narration, screen text, or production directions.
- An earlier local cache entry records a `script.v1` model draft, response
  `resp_02f45c24cc7305db016af09a4af1b087d2aec44dab382872ee`, cache key
  `f070a7a3922a7d67c40913435ff31d2156ed2dcbbe59c83df0c8620f5b23624a`.
  It contains different prose, titles, and visuals. Cache files are ignored and
  may not be present in another checkout; they are supporting audit evidence,
  not runtime dependencies.

No committed repair builder implements `script.repair.v1`. The exact original
editing command cannot be recovered from repository history. The local-edit
provenance and exact text comparisons establish the transformation below; they
do not establish who ran it or which transient command was used.

## Where each defect originates

| Symptom | Actual source and contributing behavior |
| --- | --- |
| Repeated attribution | Twelve of thirteen narration items exactly equal `"According to Searchbloom, " + claim.text[0].lower() + claim.text[1:]`. The current local repair introduced this template. Claims themselves have no such repeated prefix. `script.v1` asked for explicit attribution without teaching natural alternatives. Deterministic ranking checks and `verify.v1` require attribution within each ranking/opinion candidate, but do not require this particular wording. |
| Incorrect capitalization | `claim_004` starts `AI`, `claim_005` and `claim_010` start `Searchbloom`, `claim_011` starts `The SEO Works`, `claim_012` starts `Tinuiti`, and `claim_013` starts `Graphite`. The repair's first-character transformation yields `aI`, `searchbloom`, `the SEO Works`, `tinuiti`, and `graphite`. The source and claims retain the proper spellings. Normalization lowercases temporary comparison strings only; it does not write script text. |
| Unnatural scene titles | Scenes 4–6 use complete attributed claim sentences as titles. This is in the local script data, not Markdown formatting. The generation prompt lacked a label style and whole-scene scope requirement. Scene 5's title names Tinuiti but its narration also covers Graphite and iPullRank. Factual support for the title cannot establish that it describes the whole scene. |
| Generic visual directions | All six directions are exactly `Reveal the cited text in sequence.` The local repair supplied this repeated note. The earlier model draft had different but sometimes unsuitable visuals, including an upward chart of citations and a ranking badge. `script.v1` only said that visuals were non-factual production notes; neither structural nor factual review inspected their production suitability. |
| Weak screen text | All six scenes copy their title into their sole on-screen item. The repair erased the distinction between a topic label and a useful visual takeaway. The old prompt only requested short text. The verifier correctly checks entailment, not information design. |
| Dense narration | The claims include multi-part table summaries, such as `claim_013` combining rank, score, specialty, fee disclosure, and contract term. They are useful evidence but awkward narration when copied wholesale. The writer must select and organize approved details into spoken sentences, without altering the evidence layer. |
| Unrelated disclosure citations | `claim_072` was attached to every scene and almost every text item. The old name recall filter required the publisher name inside cited claim/source text even when it appeared solely as the reporting source. This created pressure to add the self-ranking claim to unrelated items. The record establishes the unnecessary citations and the filter behavior, but not the editor's intention. |

## Root changes

`script.v2` makes the writer responsible for a coherent scene progression, short
spoken sentences, varied explicit attribution, exact source capitalization,
neutral topic labels, concise distinct screen takeaways, and scene-specific
visual subjects/layouts/actions. It prohibits mechanical claim prefixing and
unrelated disclosure citations. The renderer remains lossless. Claim extraction,
source text, evidence IDs, and approved facts remain unchanged.

The deterministic name filter now recognizes a publisher used solely in an
explicit attribution phrase when all cited approved claims establish that
publisher in their attribution metadata. This applies only to name recall;
quantities, other companies, publisher-as-company statements, and self-ranking
statements still require cited support. The full original candidate still goes
to the independent factual verifier. Ranking attribution and verifier prompts
are unchanged, so existing exact factual caches remain usable.

`article_video/quality.py` adds a separate, versioned, deterministic editorial
report. It checks source/alias/acronym casing, dense sentences, repeated openings
and narration, sentence-like titles, lexical/citation alignment within scenes,
title scope across companies, duplicated or long screen copy, and repeated or
unanchored visuals. Suspicious charts/badges are flagged for review. These are
bounded English heuristics: they cannot prove naturalness, full semantic scene
coherence, correctness of a visual, or readiness to produce the video.

Quality reports are saved separately and embedded in the overall script review.
Their `QUALITY_*` findings use the existing exact-item acceptance gate, with a
required human note. Automatic approval requires zero findings. Review hashes
bind both kinds of checks; old script approvals become stale. Selection/facts
hashes retain their previous serialization. Voiceover recomputes the quality
review before checking the script receipt.

## Cost and artifact handling

`uv run main.py review-quality` runs without a key, upstream approvals, or model
calls. It only saves the quality report. Normal script review also runs these
checks locally, retains factual verification, and reuses exact cached verdicts.
Quality findings never trigger a retry, regeneration loop, or silent rewrite.

The current combined review was refreshed with a cache-only provider that raises
on any cache miss: all 26 factual verdicts were reused. No generation, verifier,
speech, or other external API requests were made. Existing scenes, Markdown,
facts, and approval receipts were preserved. The previous script receipt is now
stale, rather than being deleted or replaced with an invented approval.

An editorial rewrite remains required for the existing local-repair artifact.
Use the new writing contract for a deliberate script revision, then run review
and renew approval. A prompt change does not silently regenerate saved scripts.
