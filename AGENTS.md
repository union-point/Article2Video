# Repository Guidelines

## Project Structure & Module Organization

Article2Video converts articles into videos with traceable source evidence. The article extraction layer is implemented in `article_parser/`; `main.py` remains a placeholder. Dependencies are pinned in `pyproject.toml` and `uv.lock`. `.python-version` selects Python 3.13.

Read `README.md` for the implemented extraction contract. Local, ignored planning documents (`Article Parser Implementation Spec v1.md` and `Article-to-Video Automation Implementation Plan v2.md`) provide additional context when available. Place extraction code in `article_parser/`, separating fetching, parsing, sentence splitting, schemas, and validation. Keep specialized parsers in `article_parser/parsers/`, tests in `article_parser/tests/`, and saved HTML in its `fixtures/` subdirectory. Use `snapshots/` for fetched originals and `output/` for generated JSON.

## Build, Test, and Development Commands

- `uv sync`: create `.venv` and install locked dependencies.
- `uv run main.py`: run the current placeholder entry point.
- `uv add <package>` / `uv add --dev <package>`: add runtime or development dependencies.
- `uv run python -m pytest article_parser/tests`: run the parser test suite.
- `uv run python -m article_parser --html-file article_parser/tests/fixtures/searchbloom_article.html --url "<original-url>" --output output/article.json`: run offline extraction from the frozen fixture.

Use uv for environment and dependency management; commit `pyproject.toml` and `uv.lock` together. No build, lint, or formatting commands are configured yet.

## Configuration & Secrets

Keep `OPENAI_API_KEY` in the ignored `.env` file. Run commands that need it with `uv run --env-file .env main.py` (or the relevant module). Never commit or log credentials. The extraction layer does not require OpenAI calls.

## Coding Style & Naming Conventions

Use four-space indentation, `snake_case` for modules and functions, `PascalCase` for classes, and `UPPER_SNAKE_CASE` for constants. Keep modules focused. Parsers accept HTML and a URL; fetching and file writes belong in separate layers. Preserve source wording and stable sentence IDs rather than paraphrasing extracted content.

## Testing Guidelines

Use pytest with `test_*.py` files and deterministic saved HTML fixtures. Cover sentence reconstruction and offsets, unique IDs, registry matching, fallback warnings, validation failures, and mocked fetch behavior. Repeated parsing must produce identical content apart from retrieval timestamps. No numerical coverage threshold is established.

## Commit & Pull Request Guidelines

Use concise, imperative subjects such as `Add deterministic sentence splitter`. Keep changes focused. PRs should describe behavior, link relevant issues or specification sections, and report validation commands and results. Include representative JSON for extraction changes; clearly identify any checks that could not run.
