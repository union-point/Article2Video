"""Lossless wire representation; local artifacts and cache keys retain their format."""
import json


def compact_payload(payload):
    """Intern repeated headings/context globally, preserving IDs, rows and headers."""
    shared = {}
    keys = {}

    def intern(value):
        key = json.dumps(value, sort_keys=True, ensure_ascii=False)
        if key not in keys:
            ref = f"context_{len(keys) + 1}"
            keys[key] = ref
            shared[ref] = value
        return keys[key]

    def visit(value):
        if isinstance(value, list):
            return [visit(item) for item in value]
        if isinstance(value, dict):
            if {"id", "text", "section_id", "headings", "context"} <= value.keys():
                return {k: visit(v) for k, v in value.items() if k not in {"context", "headings"}} | {
                    "shared_context_ref": intern({"headings": value["headings"], "context": value["context"]})}
            return {k: visit(v) for k, v in value.items()}
        return value

    data = visit(payload)
    if not shared:
        return payload
    return {"format": "evidence-context-refs.v1", "data": data, "shared_contexts": shared,
            "reference_rule": "Each shared_context_ref expands to its headings and context. Context is interpretation only, never a substitute for citing evidence IDs."}
