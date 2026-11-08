# Stages 2–4 decisions

- Input is the frozen, validated parser artifact. Evidence IDs, offsets, and
  reconstruction are checked again without claiming a new original-HTML coverage
  measurement. Retrieval time is excluded from its content hash.
- Generation baseline: `gpt-4.1-mini-2025-04-14`. Independent verification baseline:
  `gpt-4.1-2025-04-14`. Both are configurable snapshot IDs; availability depends on
  the API account. Every result records requested and returned model IDs, response
  ID, usage, prompt version, and cache key. Every semantic check has its own record.
- Prompt versions: `selection.v2`, `facts.v1`, `script.v2`, `verify.v1`. Prompts live
  in `article_video/prompts.py`; both version and actual prompt text affect caching.
- Structured output uses OpenAI Python 2.26.0 Responses API `responses.parse`
  with strict Pydantic schemas. Refusals, incomplete output, API failures, and
  invalid evidence references fail before replacing the stage artifact. Requests
  use `store=False`, 60-second timeouts, and two SDK retries for transient errors.
  One corrective generation is attempted for structurally invalid output, with
  the validation error returned to the generator. Invalid attempts are not cached.
  Reference: [official structured-output documentation](https://developers.openai.com/api/docs/guides/structured-outputs?api-mode=responses).
- Sections use the shallowest body heading level (normally H2), including deeper
  subsections, plus the introduction. Each evidence item belongs to exactly one
  selectable section. Articles with fewer than five sections select all of them.
- A verifier sees one candidate and only its cited evidence plus structural
  context. Table row/header and ranked-profile context aid interpretation, but
  do not satisfy token matching in place of cited cells/sentences. Script checks
  additionally require entailment by approved claims. Neither verifier uses tools
  or external knowledge.
- Python quantities retain units, percentages, ratios, and explicit ranges.
  Company matching uses aliases, ranked company names, model-declared names,
  and conservative proper-name heuristics. English number parsing is deliberately
  bounded; unusual formats, ambiguous words, and names can need review. Token
  overlap cannot establish entailment, correct entity/value relationships, or
  preservation of hedges. Both Python and semantic checks run, with a human final
  decision. False positive review flags are possible.
- Review flags require explicit item IDs and a note; unknown/out-of-selection IDs,
  duplicate IDs, and invalid structure cannot be waived. Facts approval may name
  a subset of claims; only that subset reaches the script writer. Approvals bind
  the whole artifact and full review report; edits or upstream approval changes
  require renewed downstream review. Receipts record human declarations, not
  cryptographic identity verification.
- Optional `--auto-approve` is explicit per invocation, with manual checkpoints
  remaining the default. A new automatic receipt requires zero errors, zero flags,
  and supported required semantic checks. Existing valid human approvals and their
  claim subsets/accepted findings are preserved. The mode does not waive findings
  or silently discard claims. Receipts identify `mode: "automatic"` and the machine
  reviewer; the omitted human default preserves existing receipt hashes. Automatic
  full runs rebuild stale downstream inputs and stop after Stage 4.
- Searchbloom publishes and ranks its own company. Prompts preserve that caveat
  and require rankings/opinions to be attributed to Searchbloom. Ranking language
  also receives a Python attribution check; semantic review checks the meaning.
- Script target is 350–450 narration words across 6–8 scenes. Out-of-range word
  counts are review flags. Each narration sentence, title, and on-screen text item
  has claim IDs; visual directions are production notes, never display copy.
- `scenes.json` is the editable script source. `script.md` is derived for review;
  markdown edits do not alter the narration artifact or constitute approval.
- Cache entries store successful structured generations and verifier decisions,
  including negative verdicts (which are valid review results). Failures are not
  stored. Deterministic validation always reruns on cache hits. Stage output files
  and receipts remain trackable; disposable `cache/` is ignored. Writes are atomic
  per file, not a multi-file transaction; review/approval recomputes hashes.
- Tests use a synthetic second article and injected models, plus the real frozen
  article index and an HTTP-mocked call through the installed OpenAI SDK. They
  test contracts and guardrails, not real-model factual accuracy.
- On 2026-11-08, Stage 2 was run against the real article and OpenAI API. The draft
  in `output/selection.json` ranks all 15 sections and chooses seven, with no
  structural errors. Initial incomplete rankings were rejected; the final schema
  fixes the ranking array length to the catalogue size. No human approval was
  fabricated. The full downstream flow has also been exercised with deterministic
  injected models.
- On 2026-11-08, the user approved that selection in chat and its human receipt
  was saved. The live facts run produced 72 claims: 58 supported, 13 partial, and
  one unsupported, with zero structural errors and 107 review flags across 52
  claims (20 claims passed all current checks). The requested automatic mode was
  exercised on those artifacts, preserved the selection approval, and stopped on
  the facts flags. Facts remain unapproved; no live script was generated. See
  `output/facts_review_summary.md` and the full source-backed report.
- No TTS, timing, storyboard, React/Remotion, rendering, or publication is included
  in Stages 2–4. TTS settings, Remotion license, music/font licenses, and cost/time
  estimates remain decisions for their corresponding later stages.

- On 2026-11-08, the script was repaired using the 17 approved claims: 375 narration words in six scenes, one sentence per narration item, explicit publisher attribution, and cited on-screen statements. All Python and semantic checks passed with zero errors and zero flags; a machine approval receipt was recorded. No validator rules were relaxed.

- A subsequent investigation traced the current script's mechanical attribution,
  damaged capitalization, repeated visuals, and copied title/screen text to its
  `local-edit` / `script.repair.v1` provenance. The old review measured factual
  support, not editorial quality. `script.v2` now defines the writing contract,
  and a separate offline quality gate reports 34 heuristic flags on that artifact.
  The 26 factual verdicts were reused from cache; the old script approval is stale.
  No script content, facts, or receipts were rewritten and no API calls were made.
  Publisher attribution metadata now satisfies name recall only for explicit
  attribution-only uses; factual entities, numbers, and semantic checks remain
  guarded. See `docs/script_quality_investigation.md` for evidence and limits.

- At the user's request, one `script.v2` draft was generated from the unchanged
  approved facts. A provider guard prohibited corrective script generation.
  The resulting seven-scene, 340-word draft has zero structural errors, 35
  supported / five partial / one unsupported factual verdicts, and seven quality
  flags (68 combined flags). It remains unapproved; all receipts are unchanged.
  Previous and new artifacts are preserved under
  `output/script_comparisons/20261108-213650/`, with verified backup hashes and a
  comparison report. There was one generation request and 41 factual verification
  requests; upstream verdicts were cached and quality review was offline.

- The user then requested one targeted repair and a stop for approval. A direct
  local patch preserved the seven scene IDs/order and used only already-used,
  approved claim IDs. Exact values, attribution, currency labels and production
  directions were repaired; narration is 363 words. One review pass returned 44
  supported / two partial / one unsupported factual verdicts and three quality
  flags (eight combined flags, zero structural errors). Seven verdicts were
  cached and 40 changed items were verified; there were no generation calls or
  repair loops. Remaining findings were retained without acceptance, all receipts
  stayed unchanged, and no audio/video was generated. The before/after artifacts,
  exact patch, change list, preservation hashes and review summary are under
  `output/script_repairs/20261108-targeted-01/`.

- Stage 5 is implemented as the explicit `voiceover` command. The existing `run`
  behavior stops at Stage 4. It checks current script/upstream approvals without
  rewriting their artifacts and uses only approved narration text.
- The final voice settings in `voiceover_config.json` use **Alloy**, speed **1.0**,
  model `gpt-4o-mini-tts-2025-12-15`, and the user's English narrator instructions
  verbatim. No prompt experiment or A/B comparison was generated or selected.
- Speech API input was checked against official documentation: maximum 4,096
  characters, with a 2,000-token model input limit. Local `o200k_base` preflight
  includes instructions and an overhead allowance. Continuous narration is the
  default; only scene boundaries can be used for necessary splitting. Oversized
  scenes require a script edit and renewed approval.
- Raw speech and normalized audio have separate SHA-256 caches. Instructions and
  all speech settings are included in raw keys; loudness/output settings and
  FFmpeg version are included in processed keys. Final metadata links audio to the
  current script approval and stores final instructions and an AI-generated notice.
- Two-pass FFmpeg `loudnorm` targets -16 LUFS / -1.5 dBTP by default, with mono
  48 kHz 16-bit PCM output and configurable tolerances. Cache hashes and WAV
  integrity are checked. Local failures retain reusable raw speech, and paid/API
  failures do not replace existing output. Human listening review remains pending.
- Every Stage 5 API attempt, transient retry, cache event, and local normalization
  event uses the existing usage ledger. Binary WAV responses have unknown token
  usage (`null`), not zero. No synthetic billing estimates are recorded.
- Official documentation currently schedules Speech API TTS shutdown for
  2027-01-06. The configured snapshot is usable with the plan's current workflow;
  the replacement Realtime API needs a future integration change. Sources:
  [Speech API](https://developers.openai.com/api/reference/python/resources/audio/subresources/speech/methods/create),
  [model limits](https://developers.openai.com/api/docs/models/gpt-4o-mini-tts).
- Per the user's latest instruction, Stage 5 was tested exclusively with mocked
  speech/HTTP and synthetic PCM audio. No real API request, excerpt comparison,
  or full narration WAV was generated. The existing approved script is unchanged.
