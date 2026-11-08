"""Append-only usage events, without prompts, source text, headers or error bodies."""
from datetime import datetime, timezone
import json
from pathlib import Path


class UsageLog:
    def __init__(self, path: Path):
        self.path = path

    def emit(self, event, **fields):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        record = {"timestamp": datetime.now(timezone.utc).isoformat(), "event": event, **fields}
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
