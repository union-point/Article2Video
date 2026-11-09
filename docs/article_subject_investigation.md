# Article subject lost between selection and scripting

Inspected the saved Searchbloom extraction, selection, 24-claim facts artifact,
three-claim automatic receipt, script and cached verifier responses. No live model
requests or output-artifact replacements were made during this investigation.

## Stage 1: content present

The extraction contains 9 ranked entries, 3 tables and 51 headings. EvidenceIndex
preserves all relevant records and sends them to selection without text truncation:

| Section | Content | Indexed evidence records |
| --- | --- | ---: |
| block_0001 | Title, opening rankings and summary | 12 |
| block_0005 | Agency comparison, scores and table rows/headers | 54 |
| block_0025 | All nine agency profiles, ranks and their fields | 184 |
| block_0046 | Agency recommendations by situation | 36 |

The wire compaction interns repeated context; it does not drop profile text,
source IDs, table rows or headers. No parser or evidence-index change was needed.

## Stage 2: primary subject excluded

selection.v2 asked for a selective angle and preferred a coherent story, without
requiring that it preserve the article's main subject. Its angle became how to
vet agencies. Its own reasons explicitly excluded profiles as too lengthy,
recommendations as broadening into a shortlist, and scores as encouraging a
league-table framing. This deliberately changed the article's purpose.

The 5–7 section rule constrained the budget but did not force these exclusions:
all nine profiles share one selectable section. The model received the central
content and chose seven predominantly supporting sections instead. Facts then
received evidence ONLY from those selected sections, so it could not recover the
excluded rankings, profiles or scores.

## Stage 3: supported evidence disproportionately filtered

24 claims were extracted; the cached independent verifier supported 22 and marked
2 partial. Nevertheless, the automatic receipt allowed only claim_002 (case-study
sourcing), claim_003 (payment disclosure), and claim_005 (answer variability).
19 independently supported claims were excluded by deterministic heuristics.

Most failures compared attribution labels literally to the publisher identity:
labels such as “Searchbloom's recommendation”, “Searchbloom's comparison” and
“Searchbloom's published pricing” failed despite supported evidence. Claim_007
also treated the ordinary initial word “Separate” as a missing company name.
Even the agency pricing/contract facts present in the selected material were lost.
The two genuine partial verdicts concerned omitted conditions in claim_014 and
an unsupported attribution qualification in claim_021; those must remain excluded.

## Stage 4: sparse evidence padded to a hard minimum

The script received the wrong angle and only the three remaining claims. It had
no article title to anchor scope. Both the prompt and Script schema required at
least six scenes, and storyboard/Zod repeated that minimum. The result repeated
answer variability and sourcing across six scenes. The verifier correctly checked
support, not whether this was an adequate summary of the original article.

## Minimal changes

- Anchor selection to title, lead and main content, preserving the purpose of
  comparisons, tutorials, news and other article types. Select 1–7 useful sections;
  take representative facts within long central sections instead of dropping them.
- Pass article title with angle to facts and script. Prompt facts to cover central
  findings/subjects first and keep caveats proportional.
- Remove the Stage 3 lexical name/number and attribution heuristics. Existing
  structural/citation checks and the independent LLM verifier decide usability.
  This avoids inventing another attribution-matching heuristic or exemption list.
- Let script and storyboard use 2–8 scenes (title and conclusion remain supported).
  Word bounds are guidance. Tell the writer to shorten sparse evidence rather than
  repeat it. No new validators, gates, scene quotas or repair passes.
- Version the three changed prompts and include prompt version in the existing
  artifact freshness check. The next run refreshes Stages 2–4 and stale descendants,
  reusing Stage 1 and any still-applicable model/media caches. Saved outputs here
  are evidence of the old run and have not been silently replaced.

Regression checks cover untruncated profile/table inputs, title/angle propagation,
retaining LLM-supported descriptive attribution, a two-scene script through Zod,
and prompt-version refresh plus idempotent cache reuse. Mocked-provider tests
cannot establish the editorial quality of a future live generation.

Inspected artifact SHA-256 hashes (file bytes):

- `output/article.json`: `b82c47ca30a55a81d6ed3268ee2ce5fea4c38f7198784190eb83ee513f009ecc`
- `output/selection.json`: `c5569f0c1c425aaf005a31723497a6c4e320d16207a3283f523d5e5f94435671`
- `output/facts.json`: `1a7658fa229c92aede1261a8a78942e1a3a528bc6264d2115aa5aadb9ad7bc24`
- `output/approvals/facts.json`: `bdb1428bdb727b78d364241aa70868d95859c27c8e5b704307515120fbd88110`
- `output/scenes.json`: `3ceb80ff96cc086596c0ad06dd9b41bf768a62da3d94ea9bcf7220b78ebc703a`

Validation completed: 219 Python tests passed; 13 Remotion tests passed;
TypeScript typecheck and `git diff --check` passed. No paid API calls were made.
