import json
from pathlib import Path
from types import SimpleNamespace

import httpx
from openai import OpenAI
import pytest

from article_video.llm import ModelRunner, OpenAIProvider, GenerationError
from article_video.payloads import compact_payload
from article_video.schemas import Claim, Facts, Verdict
from article_video.storage import read_json, write_json


def events(runner):
    return [json.loads(line) for line in runner.usage_log.path.read_text().splitlines()]


def test_evidence_is_lossless_and_smaller(real_index):
    original = {'evidence': real_index.records(list(real_index.evidence))}
    wire = compact_payload(original)
    def expand(value):
        if isinstance(value, list):
            return [expand(v) for v in value]
        if isinstance(value, dict):
            result = {k: expand(v) for k, v in value.items() if k != 'shared_context_ref'}
            if 'shared_context_ref' in value:
                result.update(wire['shared_contexts'][value['shared_context_ref']])
            return result
        return value
    assert expand(wire['data']) == original
    assert len(json.dumps(wire)) < len(json.dumps(original)) * .7
    assert compact_payload({'claim': 'plain'}) == {'claim': 'plain'}


def test_cache_and_correction_usage_are_not_double_counted(setup_pipeline):
    p, provider = setup_pipeline
    attempts = []
    def invalid_once(data):
        attempts.append(1)
        if len(attempts) == 1:
            data.ranked_sections[0].section_id = 'invalid'
        return data
    provider.transform = invalid_once
    p.select()
    p.select()
    log = events(p.runner)
    assert len([e for e in log if e['event'] == 'provider_attempt_finished']) == 2
    assert len([e for e in log if e['event'] == 'validation_failed']) == 1
    assert [e for e in log if e['event'] == 'cache_hit'][0]['usage'] == {}
    assert sum(e.get('usage', {}).get('total_tokens', 0) for e in log) == 20
    assert len({e['call_id'] for e in log}) == 2


def test_all_transport_failures_and_retries_logged_without_credentials(tmp_path, monkeypatch):
    calls = []
    def handler(request):
        calls.append(request)
        if len(calls) == 1:
            raise httpx.ConnectError('secret error body', request=request)
        return httpx.Response(429, json={'error': {'message': 'secret error body'}})
    monkeypatch.setattr('article_video.llm.time.sleep', lambda seconds: None)
    client = OpenAI(api_key='private-test-key', http_client=httpx.Client(transport=httpx.MockTransport(handler)))
    runner = ModelRunner(tmp_path, OpenAIProvider(client))
    with pytest.raises(GenerationError):
        runner.run('facts', model='test', version='v1', prompt='private prompt', payload={}, schema=Verdict, validate=lambda v: None)
    log = events(runner)
    finished = [e for e in log if e['event'] == 'api_attempt_finished']
    assert len(calls) == len(finished) == 3
    assert [e['retrying'] for e in finished] == [True, True, False]
    assert all(e['usage'] is None for e in finished)
    assert 'secret error body' not in runner.usage_log.path.read_text()
    assert 'private-test-key' not in runner.usage_log.path.read_text()
    assert 'private prompt' not in runner.usage_log.path.read_text()


@pytest.mark.parametrize('text,status', [('bad json', 'completed'), ('{"status":"supported","reason":"ok"}', 'incomplete')])
def test_failed_parsing_and_incomplete_responses_retain_reported_usage(tmp_path, text, status):
    def handler(request):
        return httpx.Response(200, json={'id':'resp_test','object':'response','created_at':1,'status':status,
            'model':'test','output':[{'id':'msg_test','type':'message','role':'assistant','status':'completed',
                'content':[{'type':'output_text','text':text,'annotations':[]}]}],
            'usage':{'input_tokens':10,'output_tokens':5,'total_tokens':15}})
    client = OpenAI(api_key='test', http_client=httpx.Client(transport=httpx.MockTransport(handler)))
    runner = ModelRunner(tmp_path, OpenAIProvider(client))
    with pytest.raises(GenerationError):
        runner.run('script', model='test', version='v1', prompt='test', payload={}, schema=Verdict, validate=lambda v: None)
    finished = [e for e in events(runner) if e['event'] == 'api_attempt_finished']
    assert len(finished) == 1
    assert finished[0]['usage']['total_tokens'] == 15
    assert finished[0]['outcome'] == 'failure'


def prepare(p):
    p.select()
    p.approve('selection', 'test')
    p.facts()
