"""Command-line extraction; only validated artifacts are written."""
import argparse
import json
import os
from pathlib import Path
import sys
import tempfile
from urllib.parse import urlsplit

from .exceptions import ExtractionError
from .fetcher import fetch_html, load_html
from .registry import extract_article


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Extract an article with sentence-level source evidence")
    parser.add_argument("--url", required=True, help="Original URL (also resolves relative links offline)")
    parser.add_argument("--html-file", type=Path, help="Load a frozen HTML snapshot without network access")
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--snapshot-dir", type=Path, default=Path("snapshots"))
    args = parser.parse_args(argv)
    try:
        url = urlsplit(args.url)
        if url.scheme not in {"http", "https"} or not url.hostname:
            raise ExtractionError("INVALID_URL", "--url must be an absolute HTTP(S) URL")
        fetched = load_html(args.html_file, args.url) if args.html_file else fetch_html(args.url, args.snapshot_dir)
        document = extract_article(fetched.html, fetched.source)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        # Atomic replacement avoids partially written JSON if interrupted.
        temp_path = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=args.output.parent, delete=False) as handle:
                temp_path = Path(handle.name)
                payload = document.model_dump(exclude_none=True)
                payload["article"] = document.article.model_dump()
                json.dump(payload, handle, ensure_ascii=False, indent=2)
                handle.write("\n")
            os.replace(temp_path, args.output)
        finally:
            if temp_path is not None:
                temp_path.unlink(missing_ok=True)
        print(f"Parser: {document.extraction.parser_name} ({document.extraction.parser_version})")
        print(f"Fallback: {'yes' if document.extraction.fallback_used else 'no'} | Validation: {document.validation.status}")
        print("Counts: " + ", ".join(f"{k}={v}" for k, v in document.validation.counts.items()))
        for warning in document.validation.warnings:
            print(f"WARNING {warning.code}: {warning.message}")
        print(f"Output: {args.output}\nSnapshot: {fetched.source.snapshot_path}")
        return 0
    except (ExtractionError, OSError, ValueError) as exc:
        print(f"ERROR {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
