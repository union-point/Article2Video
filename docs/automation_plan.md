# Demo automation simplification

The intended command is `uv run --env-file .env main.py run --url URL`, producing
`video.mp4` and `fact_sheet.csv` without a person. This is a practical demo, so
minor timing and visual imperfections are acceptable.

Inspection found working Stages 1–8, schemas, evidence IDs, caches, normalized
speech, alignment, Remotion templates and atomic rendering. Keep these stages;
connect them with a small linear runner rather than a new execution framework.

Minimum changes:

- Make auto the default. Keep the existing manual checkpoint commands behind an
  explicit review mode; automatic runs don't create review reports.
- Use the existing approved-claim subset to exclude partially/unsupported facts.
  Preserve the original facts. Keep structural/citation checks and independent
  evidence grounding. Check the complete script once rather than verifying every
  title, sentence and display label in separate model requests.
- Remove the editorial quality subsystem and targeted draft-repair workflow,
  including their CLI commands and tests. Keep writing guidance in the prompts.
  Unsupported scripts fail; don't build another recovery system.
- Keep usable timing alignment and its scene fallback. If transcript partitioning
  or scene boundaries fail, allocate the existing audio clock by narration length.
  Don't ask for timing corrections or generate replacement TTS.
- Keep the existing LLM template planner, diagrams, text fitting and one existing
  structured-output correction attempt. Remove the redundant baseline-layout
  gate. Omit whole oversized optional labels and use a short neutral heading for
  oversized titles. No new visual-policy options or fallback chains.
- Retain schema/media compatibility, source bindings and basic output checks.
  Remove repeated full alignment as a downstream QA requirement.
- Print final paths and warnings. No status framework or new diagnostic/history
  system. Reuse valid intermediates and caches; only stale descendants change.
- Generate a two-column CSV (`video_statement`, `article_sentence`) from actual
  narration and exact article evidence, using existing claim/source IDs. Exclude
  on-screen text and duplicate statement/source pairs.

Validation: parser and pipeline suites; full offline CLI integration with mocked
paid/media providers; unsupported-fact exclusion; failed-render preservation;
resume without paid calls; timing-only changes preserving script and speech;
existing Remotion tests/typecheck. A small real local render can smoke-test media
integration without paying for new article, speech or transcription generation.

The ignored `Article-to-Video Automation Implementation Plan v2.md` retains the
historical detailed stage plan; this revision supersedes its mandatory approval,
editorial QA and manual timing requirements.

Completed validation (2026-11-09): 223 Python tests and 13 Remotion tests passed;
TypeScript typecheck and `git diff --check` passed. A real local 1920×1080,
30 fps H.264/AAC export and CSV were produced from synthetic inputs; rerunning
the URL command reused generation and rendering caches. Paid providers were
mocked, so this does not establish live model/account availability.

Article-subject follow-up: selection and fact prompts now prioritize the main
subject and receive the title; descriptive attribution is judged by the existing
LLM verifier rather than lexical heuristics. Scene contracts permit 2–8 scenes,
and word bounds are guidance. Prompt-version freshness refreshes stale Stages 2–4.
See article_subject_investigation.md for evidence and root causes.
