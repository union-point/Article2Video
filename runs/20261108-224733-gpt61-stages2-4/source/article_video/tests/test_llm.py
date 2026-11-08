from types import SimpleNamespace

import httpx
from openai import OpenAI
import pytest

from article_video.llm import GenerationError, ModelRunner, OpenAIProvider
from article_video.schemas import Verdict
from article_video.storage import read_json, write_json


def test_installed_sdk_parses_real_responses_wire_format():
    requests = []

    def handler(request):
        import json
        body = json.loads(request.content)
        requests.append(body)
        return httpx.Response(200, json={
            "id": "resp_test", "object": "response", "created_at": 1, "status": "completed",
            "error": None, "incomplete_details": None, "instructions": None, "metadata": {},
            "model": "verifier-snapshot", "output": [{"id": "msg_test", "type": "message",
                "status": "completed", "role": "assistant", "content": [{"type": "output_text",
                    "text": '{"status":"supported","reason":"Source supports the claim."}', "annotations": []}]}],
            "parallel_tool_calls": False, "temperature": 1, "tool_choice": "auto", "tools": [], "top_p": 1,
            "usage": {"input_tokens": 10, "output_tokens": 10, "total_tokens": 20,
                      "input_tokens_details": {"cached_tokens": 0}, "output_tokens_details": {"reasoning_tokens": 0}},
        })

    client = OpenAI(api_key="test-only-not-a-real-key", http_client=httpx.Client(transport=httpx.MockTransport(handler)))
    result, metadata = OpenAIProvider(client).generate(model="verifier-snapshot", prompt="Verify evidence",
        payload={"claim": "Source text"}, schema=Verdict, max_output_tokens=100)
    assert result.status == "supported"
    assert metadata["resolved_model"] == "verifier-snapshot"
    assert requests[0]["text"]["format"]["strict"] is True
    assert requests[0]["store"] is False


@pytest.mark.parametrize("status,parsed", [("incomplete", Verdict(status="supported", reason="Truncated")), ("completed", None)])
def test_refusals_and_incomplete_results_fail(status, parsed):
    class Responses:
        def parse(self, **kwargs):
            return SimpleNamespace(status=status, output_parsed=parsed)
    with pytest.raises(GenerationError):
        OpenAIProvider(SimpleNamespace(responses=Responses())).generate(model="model", prompt="test", payload={},
                                                                       schema=Verdict, max_output_tokens=10)


def test_no_key_is_needed_until_an_uncached_request(monkeypatch, tmp_path):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    runner = ModelRunner(tmp_path)
    with pytest.raises(GenerationError, match="OPENAI_API_KEY"):
        runner.run("verify", model="model", version="v1", prompt="test", payload={}, schema=Verdict, validate=lambda v: None)
    assert not list(tmp_path.rglob("*.json"))


def test_cache_keys_include_model_version_prompt_schema_inputs_and_settings(setup_pipeline):
    pipeline, provider = setup_pipeline
    runner = pipeline.runner
    kwargs = dict(model="model-a", version="v1", prompt="prompt-a", payload={"id": "one"}, schema=Verdict, validate=lambda value: None)
    runner.run("verify", **kwargs)
    runner.run("verify", **kwargs)
    assert len(provider.calls) == 1
    for key, value in [("model", "model-b"), ("version", "v2"), ("prompt", "prompt-b"), ("payload", {"id": "two"})]:
        runner.run("verify", **{**kwargs, key: value})
    assert len(provider.calls) == 5
    runner.max_output_tokens += 1
    runner.run("verify", **kwargs)
    assert len(provider.calls) == 6


def test_corrupt_cache_is_discarded_and_validators_run_on_hits(setup_pipeline):
    pipeline, provider = setup_pipeline
    pipeline.select()
    path = next((pipeline.runner.cache_dir / "selection").glob("*.json"))
    data = read_json(path)
    data["data"]["selected_section_ids"][0] = "nonexistent"
    write_json(path, data)
    pipeline.select()
    assert len(provider.calls) == 2


def test_verifier_failure_keeps_previous_stage_output(setup_pipeline):
    pipeline, provider = setup_pipeline
    pipeline.select()
    pipeline.approve("selection", "Reviewer")
    pipeline.facts()
    previous = pipeline.path("facts").read_bytes()
    original = provider.generate

    def fail(**kwargs):
        if kwargs["schema"] is Verdict:
            raise GenerationError("Temporary verifier failure")
        return original(**kwargs)

    provider.generate = fail
    with pytest.raises(GenerationError):
        pipeline.facts(force=True)
    assert pipeline.path("facts").read_bytes() == previous


def test_structural_error_gets_one_corrective_attempt(setup_pipeline):
    from article_video.schemas import Selection
    pipeline, provider = setup_pipeline
    attempts = []

    def break_once(data):
        if isinstance(data, Selection):
            attempts.append(data)
            if len(attempts) == 1:
                data.ranked_sections[0].section_id = "nonexistent"
        return data

    provider.transform = break_once
    result = pipeline.select()
    assert len(attempts) == 2
    assert provider.calls[1][1]["validation_error"]
    assert result.data.ranked_sections[0].section_id != "nonexistent"


def test_selection_response_schema_requires_the_full_catalogue(setup_pipeline):
    pipeline, provider = setup_pipeline
    original = provider.generate
    schemas = []

    def inspect(**kwargs):
        schemas.append(kwargs["schema"].model_json_schema())
        return original(**kwargs)

    provider.generate = inspect
    pipeline.select()
    ranking = schemas[0]["properties"]["ranked_sections"]
    assert ranking["minItems"] == ranking["maxItems"] == len(pipeline.index.sections)
