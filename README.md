# Article2Video

Article2Video — AI-Powered Article-to-Video Automation

Stages 1–5 are implemented: extraction, selection, verified facts, a cited
script/scene outline, and voiceover generation. Stages 2–4 use the frozen `article.json`, with explicit human
approvals before downstream work, with an optional mode to approve clean reviews
automatically. Stage 5 is an explicit command; video rendering is not implemented.

The extraction layer converts an article into normalized JSON with stable sentence
IDs, source hashes, structural locators, and validation results. It makes no OpenAI
calls. The Searchbloom parser is verified against the saved HTML in
`article_parser/tests/fixtures/searchbloom_article.html`.

`output/article.json` is the frozen extraction of that snapshot: **valid**, no
fallback, 146 blocks, 381 sentences, 51 headings, nine ranked entries, three tables,
and three images. See `output/article_review.md` for the template inspection,
coverage check, and ten shortest/longest sentences. The initial live HTTP request
returned 403; this artifact was generated offline from the user-provided snapshot.

## Setup and tests

Use Python 3.13+ and uv:

```sh
uv sync
uv run python -m pytest article_parser/tests article_video/tests
```

Dependencies are pinned in `pyproject.toml` and locked in `uv.lock`; update both
together. Tests include the real Searchbloom fixture, unrelated fictional articles,
and offline Stages 2–5 tests. `main.py` runs the Stages 2–5 CLI;
use the parser module CLI for extraction.

Keep `OPENAI_API_KEY` in the ignored `.env` for Stages 2–5. Extraction
requires no credentials or environment variables.

## Selection, facts, and script (Stages 2–4)

Configure the publisher, company aliases, exact generation/verifier model IDs,
and word limits in `pipeline_config.json`. The baseline uses
`gpt-4.1-mini-2025-04-14` for generation and `gpt-4.1-2025-04-14` for the independent
verifier. Use models available to your API account that support structured outputs.
For a different publisher, change `publisher` and review the aliases.

Run from the repository root. Common options go **before** the command:

```sh
uv run --env-file .env main.py select
# Read output/selection.json and output/selection_review.md. Edit data if needed.
uv run --env-file .env main.py approve selection --reviewer 'Your name'

uv run --env-file .env main.py facts
# Review claims, exact citations, token flags, and independent verifier results.
uv run --env-file .env main.py approve facts --reviewer 'Your name'

uv run --env-file .env main.py script
# Read output/script.md, output/scenes.json, and output/script_review.md.
uv run --env-file .env main.py approve script --reviewer 'Your name'
```

`uv run --env-file .env main.py run` resumes the flow, stopping at the next
approval. It does not grant approvals or enter Stage 5. Exit codes are `0` for
completed commands, `1` for errors, and `2` for a required human review. Explicit
`select`, `facts`, and `script` commands save drafts and exit `0` when generation
and checks complete; their artifacts still require approval. `review` exits `2`
when it finds review flags. Human review is the default.

To opt in to automatic approval for a complete run:

```sh
uv run --env-file .env main.py run --auto-approve
```

This advances through Stages 2–4 only when each review has **zero errors and zero
flags**, including supported results for every required semantic check. It pauses
on missing values/names, partial or unsupported claims, attribution findings, and
script length flags. It never accepts findings or drops claims automatically.
Existing valid human approvals are preserved, including explicit claim subsets
and individually accepted review findings. Approval receipts created by this mode
have `mode: "automatic"` and reviewer `article_video:auto-approve`; they are not
recorded as human reviews. If inputs change, stale downstream artifacts are rebuilt
and checked again. Repeated runs preserve valid receipts and reuse caches.

`select --auto-approve`, `facts --auto-approve`, and `script --auto-approve` approve
only that command's result; their upstream approvals must already exist. Omitting
the option keeps the manual workflow. `run --force --auto-approve` regenerates
selection, rebuilds any stale downstream artifacts, and applies the same review
rules throughout. No automatic mode enters Stage 5 or produces audio/video.

The same CLI is available as `uv run python -m article_video`. To keep multiple
articles separate:

```sh
uv run --env-file .env main.py \
  --article output/another_article.json --output-dir output/another \
  --cache-dir cache --config pipeline_config.json select
```

Each JSON artifact is an envelope with `stage`, input hashes, model/prompt/cache
provenance in `run`, and editable generated content in `data`. Do not edit the
provenance or input hashes. Selection uses stable section IDs from the article's
shallowest body headings, grouping deeper headings into their parent. It ranks
every section, then chooses 5–7 (all if fewer than five exist).

Representative fact content inside `facts.json` (illustrative, **not approved**):

```json
{
  "claim_id": "claim_001",
  "text": "Searchbloom's published total is 48 out of 50.",
  "source_ids": ["block_0027", "block_0028.f3.s2"],
  "attribution": "Searchbloom",
  "company_names": ["Searchbloom"]
}
```

Every fact must cite real IDs from selected sections. Whole prose/ranked blocks
are not evidence IDs; use their sentence IDs. Cite all required table cells,
including the company cell and score cell. A table row supplied as verifier
context does not count as a citation. Unknown and unselected citations are errors.

The Python recall filter normalizes English number words, percentages, currency,
ratios (`48/50` / `48 out of fifty`), ranges, and company aliases/possessives. It
flags missing quantities and names without crashing or silently accepting them.
Company detection is heuristic, not a complete named-entity recognizer. The
separate verifier checks each claim against only its citations and structural
context, covering swapped numbers/entities, ranks, attribution, hedges, and
overgeneralization. Every `partial` or `unsupported` verdict needs human review.

To approve only a subset of facts, repeat `--claim-id`; omitted claims are excluded
from script generation. To accept a review flag after inspecting its evidence,
supply its exact ID and explain the decision:

```sh
uv run --env-file .env main.py approve facts --reviewer 'Your name' \
  --claim-id claim_001 --claim-id claim_002 \
  --accept-review-item 'ID_FROM_FACTS_REVIEW' \
  --note 'Reason for accepting this specific finding after source review.'
```

Structural/citation errors cannot be accepted. Edit the `data` section and rerun
`review facts` instead. Missing-value/name flags, narrative length flags, and
semantic findings are explicit review decisions, never silent passes.

`scenes.json` contains 6–8 scenes with sentence-level narration, short on-screen
items, cited titles, and visual directions. Scene `claim_ids` must equal the union
of its text items' references. Python checks run on both links from each script
item to approved claims and to original source sentences. A semantic pass also
rejects new conclusions unsupported by the approved claims. Rankings/opinions
must retain publisher attribution; the Searchbloom self-ranking caveat matters.
The target is 350–450 narration words, with outliers flagged for review.

Edit script content in `scenes.json`, then regenerate the readable markdown:

```sh
uv run --env-file .env main.py review script
```

Editing `script.md` does not change the script artifact. Each human approval under
`output/approvals/` binds the current artifact and review report hashes. Automatic
receipts bind the same hashes; legacy receipts without `mode` remain human
approvals. Changing
content, configuration, or upstream approvals invalidates downstream approvals.
Regenerate stale stages with their explicit commands, review, and approve again.
Retain reviewed JSON, markdown, and receipts in version control; the pipeline
does not create commits on your behalf.

LLM results are cached in `cache/<stage>/<sha256>.json`, keyed by inputs, model,
prompt text/version, schema, and generation settings. Deterministic validators
always rerun; cached verifier decisions remain tied to their exact candidate and
cited evidence. Edited text triggers new verification. Use `select --force`,
`facts --force`, `script --force`, or `review facts --force` to bypass the relevant
model cache. `run --force` restarts at selection and its approval checkpoint.
Deleting cache does not delete artifacts, but review may make new API calls and
require renewed approval when the verifier report changes. Failures do not replace
existing stage outputs. Writes are atomic per file; related output files are not
one filesystem transaction.

See `workflow.json` for stage commands and [decision_log.md](decision_log.md) for
model snapshots, prompt versions, source caveats, and limits. The structured API
integration follows the [official OpenAI documentation](https://developers.openai.com/api/docs/guides/structured-outputs?api-mode=responses).

## Usage

Reproduce the frozen Searchbloom artifact without network access:

```sh
uv run python -m article_parser \
  --html-file article_parser/tests/fixtures/searchbloom_article.html \
  --url 'https://www.searchbloom.com/strategy/best-ai-seo-agency-companies-services-usa' \
  --output output/article.json
```

Parse the unrelated fixture through the default Trafilatura adapter:

```sh
uv run python -m article_parser \
  --html-file article_parser/tests/fixtures/generic_article.html \
  --url 'https://example.org/orchard' \
  --output output/generic_article.json
```

Fetch an article (original bytes are saved under `snapshots/<sha256>.html`):

```sh
uv run python -m article_parser \
  --url 'https://example.org/article' \
  --output output/another_article.json
```

The CLI prints parser, fallback status, validation status, warnings, counts, and
artifact paths. It exits nonzero on unrecoverable errors and never replaces an
existing output with a failed extraction. Successful writes are atomic. HTTP
requests use 10-second connect and 30-second read timeouts, follow redirects, and
retry 429, 5xx, and timeouts up to three attempts with 1- and 2-second backoffs.
Other HTTP errors, empty bodies, and non-HTML content types are rejected.

Keep the real HTML and its generated JSON together in version control. Downstream
scripts and fact sheets must cite this exact frozen JSON, not a fresh live fetch.

## Verified Searchbloom template

The title is `article.article-holder h1.entry-title`; the body is
`article.article-holder .entry-content.card-text`. Missing or ambiguous containers
raise `TEMPLATE_MISMATCH`; extraction never substitutes the whole body.

The nine repeated profiles use numbered `h3` headings under `h2#profiles`, followed
by `p.sb-answer` and labeled paragraphs, result lists, and sometimes attributed
quotes. Each profile becomes a `ranked_entry` with text fields; its original
heading is also preserved. Only the displayed heading supplies rank. Field types
retain paragraph/list/quote distinctions, and list fields retain depth.

All three real tables preserve headers, rows, cells, and links. There are no spans
in this fixture; unexpected spans trigger fallback rather than silently changing
cell relationships. Three editorial diagrams use their `data-lazy-src` URLs.
Images inside a ranked profile have `parent_id` and `after_field` (the number of
preceding fields), preserving their placement within the grouped entry.

Removed content is limited to inspected template widgets (`.sb-preferred-source`,
`.sb-ai-summarize`, `.sb-toc-label` and its adjacent list), non-visible scripts and
styles, and duplicate `noscript` content. Related guides and site navigation/footer
are outside the selected body. Editorial disclosures, methodology, publisher
self-ranking caveats, author note, and refresh log remain intact. Text is never
removed merely because it mentions AI, summaries, or sharing.

## Structure and evidence contract

- `fetcher.py`: network/offline loading, original snapshots, SHA-256 and source metadata.
- `schemas.py`: Pydantic models for artifacts and internal parser results.
- `parsers/`: pure HTML/URL parsers; metadata, original-DOM, and XML conversion helpers.
- `sentences.py`: whitespace normalization and pinned English pySBD splitting.
- `registry.py`: ordered specialized parser selection and validated fallback.
- `validator.py`: schema, IDs, offsets, reconstruction, coverage, and review warnings.
- `__main__.py`: CLI and output writes.
- `tests/fixtures/`: deterministic saved HTML sources.
- `output/`: generated JSON and extraction reviews.

IDs follow document order: `block_0001`, `block_0002`, etc. Sentence-bearing blocks
use `block_0001.s1`; nested list items are separate blocks with list depth. Table
cells use `block_0001.r1c1`. Ranked fields use `block_0001.f1.s1` to prevent ID
collisions between fields. Headings are cited by block ID, cells by cell ID, and
prose by sentence ID. Consumers must reject unknown evidence IDs.

Offsets are Python Unicode character offsets, with exclusive `end`, into normalized
block text or ranked field text. Joining sentence text with single spaces exactly
reproduces that text. Labels stay in ranked field text; the separate `label` is
additional structural metadata, not extra evidence. The splitter version includes
the pinned pySBD version and our offset adapter. Whitespace may collapse and entities
may decode; punctuation, wording, capitalization, and attribution are preserved.

Searchbloom provenance is `original_html`. XPath locators are captured before any
cleaning, so removed siblings cannot shift them. A ranked block's locator points
to its original heading; every field has its own locator. Ranked blocks group a
span of sibling nodes; associated images record their field position explicitly.
Trafilatura provenance is `extracted_xml`: its paths are not original-DOM paths.

Metadata reads Article/BlogPosting/NewsArticle JSON-LD (including `@graph`) first,
then HTML metadata/title elements. Missing article metadata is JSON `null`.
Relative URLs resolve against the final source URL. Offline mode uses `--url` as
the final URL and records local load time; original HTTP status and retrieval time
cannot be recovered from a standalone file. The hash always covers saved bytes,
not decoded or normalized text. Repeated extraction is identical except for load
or retrieval time.

## Validation and limitations

The word-coverage rejection threshold is **90%**. Searchbloom checks independently
collected cleaned title/body text. The real fixture preserves **6,688 / 6,688 words
(100%)**; a regression test also asserts full text equality, not just word counts.
Heading counts are checked against the same cleaned source scope.

Missing title, empty body, invalid schema, malformed/duplicate IDs, broken sentence
reconstruction or offsets, and low coverage reject the candidate. Specialized
parser exceptions or validation failures trigger Trafilatura on the exact same
HTML. Replaced output is never attributed to the specialized parser. Every such
fallback records a reason and a `FALLBACK_USED` human-review warning. Failure of
both parsers raises `FALLBACK_FAILED` and stops the CLI.

Missing author/date/cover image, fewer than 100 extracted words, heading-count
mismatches, and potentially lost structures produce warnings. Default Trafilatura
selection for an unrelated host is not marked as a replacement fallback.

Trafilatura 2.0.0's options were checked against its installed signature and upstream
documentation. Its coverage check verifies conversion of extracted XML, not original
HTML completeness. It can lose captions, hierarchy, spans, and embedded media.
Unknown XML structures and potentially unsupported source structures raise review
warnings; lost structure is not invented. The unrelated fixture has a documented
caption-loss warning; see `output/generic_review.md`.

English sentence splitting is used for all input; non-English articles need a
language-specific splitter. Searchbloom selectors target the inspected template,
not every page the publisher may produce. No images are downloaded. No anti-bot,
browser automation, proxy, LLM, or video work is included in the extraction layer.

## Add a specialized parser

Implement `ArticleParser` in `parsers/base.py` (`name`, `version`, `matches(url)`,
`parse(html, url) -> ParsedArticle`), then add one instance to `SPECIALIZED_PARSERS`
in `registry.py`. First match wins. No fetch or file writes belong in a parser.
Use the shared splitter, emit deterministic IDs and section paths, include
independently measured cleaned-container text and heading count, and use correct
provenance with snapshot locators. Add fixture tests for the template and failure
modes. Change parser/splitter versions when extraction or segmentation changes.

## Targeted repairs and API usage

`uv run --env-file .env main.py repair-facts` repairs only claims with current
review flags, one independent claim per request. Use repeated `--claim-id` options
to choose a flagged subset. Requests include that claim, its findings, cited
prose/profile or table rows and headers, and nearby headings. Additional relevant
selected evidence can be supplied with repeated `--source-id` options. Unknown or
unselected IDs are rejected. This command never drops claims or regenerates clean
claims. It performs one repair pass, then reruns the full fact checks and semantic
verification (unchanged candidates may reuse exact cached verdicts).

Results go to `facts_repaired.json` and `facts_repaired_review.json` / `.md`.
Per-claim generation provenance is saved under `output/repairs/`. Original facts,
scripts, reports, and approvals are not replaced. A clean input is a no-op. Inspect
the separate draft before explicitly applying its changed claims to `facts.json`
and renewing review/approval; the command does not promote or auto-approve drafts.
Remaining findings remain review flags.

API payloads use lossless shared references for repeated evidence headings and
context, including complete table rows and headers. IDs and exact evidence text
are retained. This affects wire serialization only: artifact schemas, existing
cache keys, cached verdicts, and approval hashes remain compatible.

`cache/usage.jsonl` is an append-only local usage ledger. Events identify stage,
operation, model, cache key, call ID, generation attempt, and API attempt. They
record cache hits/misses/bypasses/invalid entries, validation corrections, each
transport success/failure and retry, and response IDs and token usage when returned.
Verification events are attributed to the owning facts/script stage. SDK retries
are disabled and the same allowance of two transient retries is handled explicitly
so each attempt is visible. Injected test providers produce provider events rather
than claiming to be API calls.

For totals, sum `usage` only on `api_attempt_finished` events; `generation_failed`
is a summary event, not an additional request. Cache hits have empty usage and do
not re-count historical tokens. `usage: null` means the API did not provide usage
(e.g. a connection failure); it does **not** assert zero billed tokens. An interrupted
process can leave an attempt-start event without a finish. Past attempts cannot
be reconstructed retroactively. The ledger excludes credentials, prompts, source
text, response bodies, and raw exception messages. Keep the ledger when clearing
response caches if you want to retain usage history.


## Voiceover (Stage 5)

Install FFmpeg (including its `loudnorm` filter) on your system, then use the
approved script to generate narration explicitly:

```sh
uv run --env-file .env main.py voiceover
# Alternate settings file:
uv run --env-file .env main.py voiceover --voiceover-config voiceover_config.json
# Intentionally regenerate paid speech, bypassing both audio caches:
uv run --env-file .env main.py voiceover --force
```

The existing `run` and `run --auto-approve` commands still stop after Stage 4.
Voiceover checks the entire evidence chain and current script approval before
speech generation. It reuses exact cached semantic verdicts and always reruns
Python checks. It reads narration from `scenes.json`, in scene/sentence order;
headings, on-screen text, and production notes are excluded. It does not edit or
approve the script. Modified or unapproved scripts must be reviewed first.

`voiceover_config.json` contains the final user-supplied instructions verbatim,
Alloy voice, speed `1.0`, and the pinned `gpt-4o-mini-tts-2025-12-15` model. Model,
voice, instructions, speed, API limits, tokenizer, retry/timeout settings, FFmpeg
executable, output sample rate/channels, and loudness settings are configurable.
There is no automatic voice/speed tuning or A/B selection.

The full narration uses one continuous speech request when it fits both the
4,096-character Speech API limit and configured 2,000-token model limit. Local
`o200k_base` token counting includes instructions plus a configurable overhead
allowance; it is preflight validation, not billed usage. `tiktoken` may download
its encoding data once on first use, then reuses its disk cache. If needed,
requests are split only at scene boundaries with identical settings and joined
without trimming pauses. A single oversized scene fails before speech is sent;
edit and reapprove it instead of silently altering narration.

Outputs are `narration.wav`, `narration.txt` (the exact speech input plus a final
newline), and `narration.json`. WAV output defaults to mono, 48 kHz, 16-bit PCM,
normalized in two FFmpeg passes to -16 LUFS with a -1.5 dBTP ceiling; a final
measurement checks the result. Metadata records the script and approval hashes,
full settings/instructions, audio hash, segment cache provenance, measurements,
and AI-generated disclosure. A human listening review is still pending; Stage 6
transcription/alignment will be needed to assess spoken-text accuracy. Automated
WAV/loudness checks do not establish pronunciation or verbatim speech fidelity.

Raw speech lives in `cache/voiceover/raw/<hash>.wav` with a JSON manifest. Its key
includes the exact input, model, voice, speed, response format, instructions, and
TTS version. Normalized audio is cached separately under `cache/voiceover/`, keyed
by raw segment keys, output/loudness settings, FFmpeg version and processing
version. Changing only loudness reuses paid speech. A valid normalized cache hit
needs no raw-cache files or new speech requests. Every hit verifies the stored
WAV and hash. Failed requests, malformed audio, or failed normalization never
replace existing output; valid raw speech survives local normalization failures.
Writes are atomic per file, rather than one transaction across all output files.

Stage 5 appends to the existing `cache/usage.jsonl` ledger with stage `voiceover`:
API attempt start/finish, failures/retries, request IDs, character counts, audio
bytes and cache/local-processing events. Binary WAV responses expose no token
usage, so the ledger records `usage: null`, never an invented token total. Mock
providers use provider events. Cached results use empty usage and incur no new
speech charge. Prompts, narration text and credentials are excluded from the log.

The existing Speech API is currently supported but its TTS models are scheduled
to shut down on **January 6, 2027**. This implementation follows the plan's Speech
API workflow; migrating to the recommended Realtime API requires a separate
workflow change, not merely a different model ID. See the [official speech API
reference](https://developers.openai.com/api/reference/python/resources/audio/subresources/speech/methods/create)
and [model limits](https://developers.openai.com/api/docs/models/gpt-4o-mini-tts).

Stage 5 was tested using mocked HTTP/speech responses and synthetic audio. No
real speech request or full narration was generated during implementation.
