# Article2Video

Article2Video — AI-Powered Article-to-Video Automation

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
uv run python -m pytest article_parser/tests
```

Dependencies are pinned in `pyproject.toml` and locked in `uv.lock`; update both
together. The suite currently has 58 passing tests, including the real Searchbloom
fixture and an unrelated fictional fixture. `main.py` remains the original
placeholder; use the module CLI for extraction.

Keep `OPENAI_API_KEY` in the ignored `.env` for later pipeline stages. Extraction
requires no credentials or environment variables.

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
browser automation, proxy, LLM, or video work is included.

## Add a specialized parser

Implement `ArticleParser` in `parsers/base.py` (`name`, `version`, `matches(url)`,
`parse(html, url) -> ParsedArticle`), then add one instance to `SPECIALIZED_PARSERS`
in `registry.py`. First match wins. No fetch or file writes belong in a parser.
Use the shared splitter, emit deterministic IDs and section paths, include
independently measured cleaned-container text and heading count, and use correct
provenance with snapshot locators. Add fixture tests for the template and failure
modes. Change parser/splitter versions when extraction or segmentation changes.
