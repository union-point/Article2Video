import json
from pathlib import Path
from types import SimpleNamespace

import httpx
from openai import OpenAI
import pytest

from article_video.llm import ModelRunner, OpenAIProvider, GenerationError
from article_video.payloads import compact_payload
from article_video.repairs import repair_facts
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


def test_targeted_repairs_preserve_valid_claims_and_original_files(setup_pipeline):
    p, provider = setup_pipeline
    prepare(p)
    raw = read_json(p.path('facts'))
    raw['data']['claims'][0]['text'] = 'Acme reports 999.'
    write_json(p.path('facts'), raw)
    original = p.path('facts').read_bytes()
    original_generate = provider.generate
    def generate(**kwargs):
        if kwargs['schema'] is Claim:
            payload = kwargs['payload']
            assert payload['claim']['claim_id'] == 'claim_001'
            assert 'draft' not in payload
            assert {e['section_id'] for e in payload['evidence']} == {'block_0002'}
            result = Claim.model_validate(raw['data']['claims'][1])
            result.claim_id = 'claim_001'
            result.source_ids = ['block_0003.s1']
            return result, {'resolved_model':'test','response_id':'repair','usage':{'total_tokens':20}}
        return original_generate(**kwargs)
    provider.generate = generate
    repaired, report = repair_facts(p)
    assert not report.errors and not report.flags
    assert [c.model_dump() for c in repaired.data.claims[1:]] == raw['data']['claims'][1:]
    assert p.path('facts').read_bytes() == original
    assert not (p.output_dir / 'approvals/facts.json').exists()
    assert len(repaired.data.claims) == len(raw['data']['claims'])


def test_clean_approved_repair_is_noop(setup_pipeline):
    p, provider = setup_pipeline
    p.run(auto_approve=True)
    before = {f: f.read_bytes() for f in p.output_dir.rglob('*') if f.is_file()}
    calls = len(provider.calls)
    repair_facts(p)
    assert len(provider.calls) == calls
    assert all(f.read_bytes() == content for f, content in before.items())
    assert not (p.output_dir / 'facts_repaired.json').exists()


def test_repaired_claim_is_still_semantically_verified(setup_pipeline):
    p, provider = setup_pipeline
    prepare(p)
    raw = read_json(p.path('facts'))
    raw['data']['claims'][0]['text'] = 'Acme reports 999.'
    write_json(p.path('facts'), raw)
    generate = provider.generate
    def repair(**kwargs):
        if kwargs['schema'] is Claim:
            claim = Claim.model_validate(raw['data']['claims'][0])
            claim.text = 'Acme reports that the process is guaranteed.'
            return claim, {'resolved_model':'test','response_id':'repair','usage':{}}
        if kwargs['schema'] is Verdict and kwargs['payload']['candidate']['text'].endswith('guaranteed.'):
            return Verdict(status='unsupported',reason='Guarantee not in evidence'), {'resolved_model':'test','response_id':'v','usage':{}}
        return generate(**kwargs)
    provider.generate = repair
    _, report = repair_facts(p)
    assert any(f.code == 'SEMANTIC_REVIEW' and f.target == 'claim_001' for f in report.flags)
    assert not (p.output_dir / 'approvals/facts.json').exists()


def test_repair_cannot_change_ids_or_cite_unprovided_evidence(setup_pipeline):
    p, provider = setup_pipeline
    prepare(p)
    raw = read_json(p.path('facts'))
    raw['data']['claims'][0]['text'] = 'Acme reports 999.'
    write_json(p.path('facts'), raw)
    original = p.path('facts').read_bytes()
    generate = provider.generate
    def repair(**kwargs):
        if kwargs['schema'] is Claim:
            claim = Claim.model_validate(raw['data']['claims'][0])
            claim.source_ids = ['block_0005.s1']  # Valid article evidence, outside supplied scope.
            return claim, {'resolved_model':'test','response_id':'repair','usage':{}}
        return generate(**kwargs)
    provider.generate = repair
    with pytest.raises(ValueError, match='outside its supplied scope'):
        repair_facts(p)
    assert p.path('facts').read_bytes() == original
    assert not (p.output_dir / 'facts_repaired.json').exists()


def test_repair_table_scope_keeps_complete_row_and_headers(real_index):
    from article_video.repairs import relevant_ids
    claim = Claim(claim_id='claim_table',text='Searchbloom scored 48.',
                  source_ids=['block_0007.r2c3'],attribution='Searchbloom',company_names=['Searchbloom'])
    scope = relevant_ids(real_index, claim, list(real_index.sections))
    assert 'block_0007.r2c2' in scope  # Company in same row.
    assert 'block_0007.r1c3' in scope  # Score header.
    assert 'block_0007.r3c2' not in scope  # Unrelated company's row.
