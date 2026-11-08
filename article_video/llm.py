"""Small injectable Responses API adapter and content-addressed successful results."""
import json
import os
import time
import uuid
from pathlib import Path
from typing import Callable

from openai import APIConnectionError, APIError, OpenAI
from pydantic import ValidationError

from .payloads import compact_payload
from .usage import UsageLog
from .schemas import Model, RunInfo
from .storage import digest, read_json, write_json


class GenerationError(ValueError):
    pass


class OpenAIProvider:
    logs_api_attempts = True
    def __init__(self, client=None):
        self.client = client

    def generate(self, *, model, prompt, payload, schema, max_output_tokens, log=None):
        if self.client is None:
            if not os.environ.get("OPENAI_API_KEY"):
                raise GenerationError("OPENAI_API_KEY is required for an uncached model request; use uv run --env-file .env")
            self.client = OpenAI(timeout=60.0, max_retries=0)
        emit = log or (lambda *args, **kwargs: None)
        # Disable hidden SDK retries so every transport attempt has its own event.
        client = self.client.with_options(max_retries=0) if isinstance(self.client, OpenAI) else self.client
        for attempt in range(1, 4):
            emit("api_attempt_started", api_attempt=attempt)
            usage = None
            status = None
            response_id = None
            try:
                kwargs = dict(model=model, instructions=prompt,
                              input=json.dumps(compact_payload(payload), ensure_ascii=False, separators=(",", ":")),
                              text_format=schema, max_output_tokens=max_output_tokens, store=False)
                if isinstance(client, OpenAI):
                    raw = client.responses.with_raw_response.parse(**kwargs)
                    body = raw.http_response.json()
                    usage = body.get("usage")
                    response_id = body.get("id")
                    status = raw.status_code
                    response = raw.parse()
                else:
                    response = client.responses.parse(**kwargs)
                if usage is None and getattr(response, "usage", None):
                    usage = response.usage.model_dump()
                response_id = getattr(response, "id", response_id)
                if response.status != "completed" or response.output_parsed is None:
                    raise GenerationError("Model refused, returned no structured output, or did not complete")
            except Exception as exc:
                retryable = False
                if isinstance(exc, APIError):
                    status = getattr(exc, "status_code", None)
                    retryable = isinstance(exc, APIConnectionError) or (status is not None and (status in {408, 409, 429} or status >= 500))
                    http_response = getattr(exc, "response", None)
                    if http_response is not None:
                        retry_header = http_response.headers.get("x-should-retry")
                        if retry_header is not None:
                            retryable = retry_header == "true"
                        try:
                            usage = http_response.json().get("usage")
                        except (ValueError, AttributeError):
                            pass
                retrying = retryable and attempt < 3
                emit("api_attempt_finished", api_attempt=attempt, outcome="failure",
                     error_type=type(exc).__name__, http_status=status, response_id=response_id,
                     usage=usage, retrying=retrying)
                if retrying:
                    delay = 2 ** (attempt - 1)
                    if http_response is not None:
                        try:
                            retry_after = float(http_response.headers.get("retry-after-ms", "nan")) / 1000
                            if not 0 < retry_after <= 60:
                                retry_after = float(http_response.headers.get("retry-after", "nan"))
                            if 0 < retry_after <= 60:
                                delay = retry_after
                        except ValueError:
                            pass
                    time.sleep(delay)
                    continue
                if isinstance(exc, (APIError, ValidationError, ValueError)):
                    raise GenerationError(f"OpenAI request failed ({type(exc).__name__}, HTTP {status or 'n/a'})") from None
                raise
            emit("api_attempt_finished", api_attempt=attempt, outcome="success",
                 http_status=status, response_id=response_id, usage=usage, retrying=False)
            usage = usage or {}
            return response.output_parsed, {
                "resolved_model": response.model, "response_id": response.id,
                "usage": {k: usage[k] for k in ("input_tokens", "output_tokens", "total_tokens") if k in usage},
            }


class ModelRunner:
    def __init__(self, cache_dir: Path, provider=None, max_output_tokens=14000):
        self.cache_dir = cache_dir
        self.provider = provider or OpenAIProvider()
        self.max_output_tokens = max_output_tokens
        self.usage_log = UsageLog(cache_dir / "usage.jsonl")

    def run(self, stage: str, *, model: str, version: str, prompt: str, payload,
            schema: type[Model], validate: Callable, force=False, usage_stage=None):
        key = digest({"model": model, "prompt_version": version, "prompt": prompt,
                      "payload": payload, "schema": schema.model_json_schema(),
                      "max_output_tokens": self.max_output_tokens, "validation_attempts": 2})
        path = self.cache_dir / stage / f"{key}.json"
        call_id = uuid.uuid4().hex
        def emit(event, **fields):
            self.usage_log.emit(event, stage=usage_stage or stage, operation=stage, model=model, cache_key=key, call_id=call_id, **fields)

        if path.exists() and not force:
            try:
                cached = read_json(path)
                data = schema.model_validate(cached["data"])
                info = RunInfo.model_validate(cached["run"])
                if info.cache_key != key or info.requested_model != model or info.prompt_version != version:
                    raise ValueError("Cache metadata mismatch")
                validate(data)  # Always rerun deterministic validators, even on a hit.
                emit("cache_hit", usage={}, cached_response_id=info.response_id)
                return data, info
            except (ValueError, KeyError, TypeError):
                # An invalid cache entry is never trusted or reused.
                emit("cache_invalid")
                path.unlink(missing_ok=True)
        emit("cache_bypass" if force else "cache_miss")
        request_payload = payload
        for attempt in range(2):
            def attempt_log(event, **fields):
                emit(event, generation_attempt=attempt + 1, **fields)
            kwargs = dict(model=model, prompt=prompt, payload=request_payload,
                          schema=schema, max_output_tokens=self.max_output_tokens)
            try:
                if getattr(self.provider, "logs_api_attempts", False):
                    data, metadata = self.provider.generate(**kwargs, log=attempt_log)
                else:
                    attempt_log("provider_attempt_started")
                    data, metadata = self.provider.generate(**kwargs)
                    attempt_log("provider_attempt_finished", outcome="success", usage=metadata.get("usage"))
            except Exception as exc:
                if not getattr(self.provider, "logs_api_attempts", False):
                    attempt_log("provider_attempt_finished", outcome="failure", usage=None, error_type=type(exc).__name__)
                emit("generation_failed", generation_attempt=attempt + 1, error_type=type(exc).__name__)
                raise
            raw = data.model_dump() if isinstance(data, Model) else data
            try:
                data = schema.model_validate(raw)
                validate(data)
                break
            except ValueError as exc:
                emit("validation_failed", generation_attempt=attempt + 1, retrying=attempt == 0)
                if attempt == 1:
                    raise
                request_payload = {"original_input": payload, "previous_output": raw,
                                   "validation_error": str(exc),
                                   "correction": "Return a corrected complete output satisfying the original instructions and validation error."}
        # Invalid generations and API failures never enter the cache.
        info = RunInfo(requested_model=model, prompt_version=version, cache_key=key, **metadata)
        write_json(path, {"data": data.model_dump(), "run": info.model_dump()})
        return data, info
