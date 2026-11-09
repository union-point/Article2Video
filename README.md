# Article2Video

Turn an article URL into a narrated 1920×1080 H.264/AAC MP4 and a cited fact sheet:

```sh
uv sync
npm --prefix video ci
# Install FFmpeg/ffprobe and put OPENAI_API_KEY in the ignored .env file.
uv run --env-file .env main.py run --url 'https://example.org/article'
```

The default is unattended. The final line names `output/video.mp4` and
`output/fact_sheet.csv`; any warnings print alongside it. No human approval or
review report is needed to finish. The existing Remotion templates, source IDs,
JSON schemas and content-addressed caches remain in use.

Set the publisher/company aliases and model IDs in `configs/pipeline_config.json` for your
source. `configs/voiceover_config.json` controls voice and loudness; `configs/timing_config.json`
controls transcription/alignment. Existing model IDs are retained; availability
still depends on your account. This change doesn't install or introduce frameworks.

For the saved Searchbloom source, run the same pipeline without fetching:

```sh
uv run --env-file .env main.py run \
  --url 'https://www.searchbloom.com/strategy/best-ai-seo-agency-companies-services-usa' \
  --html-file article_parser/tests/fixtures/searchbloom_article.html
```

For an existing extraction, use `main.py --article PATH run`. Common path/config
options go before the command; `run --url URL` writes `article.json` under the
chosen `--output-dir`. The same URL reuses that frozen extraction. To fetch a new
copy, remove its local `article.json` first or choose another output directory.
Use separate output directories to retain complete videos for different articles.

## What the demo does

1. Extract the article and rank/select its relevant sections.
2. Extract cited facts. Keep only claims supported by the independent verifier and
   structural and citation checks. Rejected claims remain in the original
   facts artifact but are excluded from the subset passed to the script.
3. Write a cited script with short display text and 2–8 scenes, sized to the evidence. Check structure and grounding
   once for the whole script. Unsupported scripts fail clearly; there are no
   automatic editorial rewrites or repair loops.
4. Generate and normalize narration, then transcribe and align it locally.
   Uncertain matches use deterministic scene timing with word cues disabled.
5. Let the existing LLM planner choose the existing visual templates and diagrams.
   Omit overlong optional labels, retain short complete strings, and use a neutral
   heading when a title is too long. Text fitting remains in the templates.
6. Render locally, check MP4 codecs/tracks/dimensions/duration, and export a CSV
   with just `video_statement` and `article_sentence`. Each narration statement
   appears beside its exact supporting article sentence(s), one row per unique
   statement/sentence pair. On-screen text is excluded.

Timing estimates, transitions and visual polish are acceptable demo limitations.
The pipeline retains source hashes, citations, model/prompt provenance, schema
validation, normalized audio and atomic rendering. It no longer runs editorial
quality heuristics, generates automatic review reports, or offers a draft-repair
workflow. Prompts carry the writing and visual-quality guidance.

## Resume and optional review

Rerun the same command to resume. Valid artifacts/checkpoints and model, speech,
transcription and rendering caches are reused. A timing-only change reuses the
script and speech. Individual `select`, `facts`, `script`, `voiceover`, `timing`,
`storyboard` and `render` commands remain available. `--force` bypasses that
command's cache; on `run` it restarts selection and rebuilds stale descendants.
A stale MP4 is replaced only after the new render passes its media check.
Intermediate JSON/audio remain available in the output directory and caches.

For the existing manual inspection workflow, explicitly choose review mode:

```sh
uv run --env-file .env main.py run --mode review
uv run --env-file .env main.py approve selection --reviewer 'Your name'
# Rerun review mode and inspect/approve facts, then script, if desired.
```

`review selection|facts|script` writes a report only when explicitly requested.
Existing human and automatic receipts remain supported as content-bound cache
checkpoints. Auto mode never treats a human exception as support for an
unsupported claim. Detailed review findings and manual acknowledgements belong
to this optional workflow, not the URL-to-MP4 path.

Exit codes: `0` completed, `1` failure, `2` a requested review checkpoint.

## Tests

```sh
uv run python -m pytest article_parser/tests article_video/tests
npm --prefix video test
npm --prefix video run typecheck
```

Tests use frozen articles and mocked paid providers, including a complete CLI run,
source-backed CSV output, exclusion of unsupported facts, timing fallbacks,
failed-render preservation, and resume without new generation. No live API run is
required to test the pipeline.

The simplification plan is in `docs/automation_plan.md`. Parser details follow.

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

The subject-loss investigation and prompt changes are documented in
[article_subject_investigation.md](docs/article_subject_investigation.md).
Selection preserves the article's main purpose and can choose 1–7 sections;
long sections supply representative facts. Prompts receive the article title,
and sparse evidence produces shorter scripts rather than repeated scenes.
Changed prompt versions refresh stale Stages 2–4 on the next run.
