# Article2Video

Turn an article into a narrated video with animated visuals, captions, and a source-backed fact sheet. Article2Video carries evidence from the original text through the script to the final export, making the video's claims easy to check.

## Deliverables

- [Video script](deliverables/script.md)
- [Fact sheet](deliverables/fact_sheet.csv)
- [Decision log](deliverables/decision_log.md)
- [Producing the next 10 videos](deliverables/next_10_videos.md)

## Example output

The example uses Searchbloom's **Best AI SEO Companies in 2026 (AEO and GEO)** article:

- [Video script](output/script.md)
- [Fact sheet](output/fact_sheet.csv), pairing narration statements with exact source sentences
- Local video: `output/video.mp4` — approximately 2 minutes 48 seconds, 1920×1080 at 30 fps. The MP4 is generated locally and is not tracked in Git.

The [saved article](article_parser/tests/fixtures/searchbloom_article.html) is included to reproduce the example input.

## Key features

- Extracts articles from a URL or saved HTML, preserving source wording and citations.
- Selects relevant content and generates a script from independently verified claims.
- Produces AI narration with normalized audio and synchronized sentence captions.
- Builds animated scenes using reusable visual templates, including comparisons and statistics.
- Renders a Full HD H.264/AAC MP4 and exports a CSV connecting narration to its evidence.
- Runs end to end from one command, with resumable execution and optional human review.

## How it works

```text
Article → Extract and verify facts → Write script → Generate narration
        → Align captions and plan visuals → Render MP4 + export fact sheet
```

Python handles extraction, content generation, and orchestration. OpenAI models generate and verify content, synthesize speech, and transcribe the narration; Remotion renders the video locally.

## Quick start

Run commands from the repository root. Prerequisites:

- Python 3.13 and uv
- Node.js 22.13+ within the 22.x release line, or Node.js 24+, with npm
- FFmpeg and ffprobe available on `PATH`
- An OpenAI API key with access to the models configured in `configs/`

Install dependencies:

```sh
uv sync
npm --prefix video ci
```

Create an ignored `.env` file in the repository root:

```dotenv
OPENAI_API_KEY=your_api_key
```

Generate a video from the included article snapshot:

```sh
uv run --env-file .env main.py run \
  --url 'https://www.searchbloom.com/strategy/best-ai-seo-agency-companies-services-usa' \
  --html-file article_parser/tests/fixtures/searchbloom_article.html
```

This uses saved HTML instead of fetching the article; content generation, speech, and transcription still require API access and incur usage charges. The default run completes without manual approval and prints the final video and fact-sheet paths.

To process a live article, supply its URL and omit `--html-file`. Configure the source's publisher and company aliases in [pipeline_config.json](configs/pipeline_config.json); this file also selects the generation and verification models. Voice settings are in [voiceover_config.json](configs/voiceover_config.json), and transcription settings are in [timing_config.json](configs/timing_config.json). Model access depends on your account.

Interactive runs show a compact Rich stage display and a rendering bar driven by Remotion progress. Redirected output uses plain stage results without animation or ANSI escapes. Add `--verbose` before or after the subcommand for cache/generation details and the diagnostic usage-log path; detailed request events remain in the existing cache usage log. Warnings, including excluded facts and approximate timing, appear with the final output paths.

Rerun the same command to resume. Use `--output-dir PATH` **before** `run` to keep another article's outputs in a separate directory.

## Generated outputs

Files are written to `output/` by default:

| File | Purpose |
| --- | --- |
| `video.mp4` | Final 1920×1080 video with narration and captions |
| `fact_sheet.csv` | Narration statements paired with exact supporting article sentences |
| `script.md` | Readable scene-by-scene video script |
| `narration.wav` | Normalized voiceover audio |
| `article.json` | Extracted article and source evidence |
| `storyboard.json` | Visual scene plan used by the renderer |

## Tech stack

- **Python 3.13**, uv, Pydantic
- **Beautiful Soup, lxml, Trafilatura, pySBD** for article extraction and sentence splitting
- **OpenAI API** for structured generation, verification, text-to-speech, and Whisper transcription
- **Remotion, React, TypeScript, Zod** for visual templates and video rendering
- **FFmpeg / ffprobe** for audio processing and media verification
