"""Stage 6: deterministic alignment, approval gates and mocked transcription."""
import json
from pathlib import Path
import re

import httpx
from openai import OpenAI
import pytest

from article_video.alignment import align_script, alignment_text, script_sentences, validate_timings
from article_video.pipeline import ReviewRequired
from article_video.storage import read_json, write_json
from article_video.timing import TimingConfig, TimingGenerator
from article_video.transcription import OpenAITranscriptionProvider, Transcript, validate_transcript
from article_video.voiceover import VoiceoverConfig, VoiceoverGenerator
from .test_voiceover import FakeNormalizer, FakeSpeech


def transcript_for(script, duration=2):
    text = ' '.join(i.text for s in script.scenes for i in s.narration)
    tokens = text.split()
    step = (duration - .1) / len(tokens)
    return Transcript(text=text, duration=duration, words=[
        {'word': token, 'start': i * step, 'end': (i + .8) * step} for i, token in enumerate(tokens)])


class FakeTranscription:
    def __init__(self, transcript):
        self.transcript = transcript
        self.calls = 0
        self.fail = False
        self.callback = None

    def transcribe(self, audio, config, log):
        self.calls += 1
        if self.callback:
            self.callback()
        if self.fail:
            raise ValueError('mock transcription failure')
        return self.transcript, {'requested_model': config.model, 'resolved_model': None,
                                 'request_id': 'mock', 'usage': None}


@pytest.fixture
def timing_setup(setup_pipeline):
    p, provider = setup_pipeline
    p.run(auto_approve=True)
    config = VoiceoverConfig.model_validate(read_json(Path(__file__).resolve().parents[2] / 'voiceover_config.json'))
    VoiceoverGenerator(p, config, FakeSpeech(), FakeNormalizer()).generate()
    artifact, _ = p.approved_script()
    transcriber = FakeTranscription(transcript_for(artifact.data))
    return p, TimingConfig(), transcriber, provider


def test_generation_is_monotonic_cached_and_preserves_inputs(timing_setup):
    p, config, provider, semantic = timing_setup
    before = {f: f.read_bytes() for f in p.output_dir.rglob('*') if f.is_file()}
    calls = len(semantic.calls)
    gen = TimingGenerator(p, config, provider)
    result = gen.generate()
    assert result['status'] == 'valid' and result['sentence_count'] == 6
    assert result['duration_frames'] == 66
    assert result['scenes'][0]['start'] == 0 and result['scenes'][-1]['end'] == 2
    assert all(f.read_bytes() == content for f, content in before.items())
    assert len(semantic.calls) == calls and provider.calls == 1
    assert gen.generate() == result and provider.calls == 1
    config.fps = 24
    second = gen.generate()
    assert second['duration_frames'] == 54 and second['cache_key'] != result['cache_key']
    assert provider.calls == 1
    events = [json.loads(line) for line in p.runner.usage_log.path.read_text().splitlines()]
    assert any(e['stage'] == 'timing' and e['event'] == 'cache_hit' and e['usage'] == {} for e in events)


@pytest.mark.parametrize('change', ['receipt', 'script', 'text', 'audio', 'metadata', 'upload', 'semantic_cache'])
def test_preflight_rejects_invalid_inputs_before_request(timing_setup, change):
    p, config, provider, semantic = timing_setup
    calls = len(semantic.calls)
    if change == 'receipt':
        (p.output_dir / 'approvals/script.json').unlink()
    elif change == 'script':
        document = read_json(p.path('script'))
        document['data']['scenes'][0]['narration'][0]['text'] += ' Changed.'
        write_json(p.path('script'), document)
    elif change == 'text':
        (p.output_dir / 'narration.txt').write_text('Wrong narration')
    elif change == 'audio':
        (p.output_dir / 'narration.wav').write_bytes(b'bad audio')
    elif change == 'metadata':
        document = read_json(p.output_dir / 'narration.json')
        document['inputs']['script_approval'] = 'stale'
        write_json(p.output_dir / 'narration.json', document)
    elif change == 'upload':
        config.max_audio_bytes = 1
    else:
        for path in (p.runner.cache_dir / 'verify').glob('*.json'):
            path.unlink()
    with pytest.raises((ValueError, ReviewRequired)):
        TimingGenerator(p, config, provider).generate()
    assert provider.calls == 0 and len(semantic.calls) == calls
    assert not (p.output_dir / 'timings.json').exists()


def test_force_failure_and_concurrent_edit_preserve_previous_results(timing_setup):
    p, config, provider, _ = timing_setup
    gen = TimingGenerator(p, config, provider)
    gen.generate()
    outputs = {p.output_dir / name: (p.output_dir / name).read_bytes()
               for name in ['transcript.json', 'timings.json', 'timing_review.md']}
    provider.fail = True
    with pytest.raises(ValueError):
        gen.generate(force=True)
    assert provider.calls == 2
    assert all(path.read_bytes() == data for path, data in outputs.items())
    provider.fail = False
    provider.callback = lambda: (p.output_dir / 'approvals/script.json').unlink()
    with pytest.raises(ValueError, match='changed during'):
        gen.generate(force=True)
    assert all(path.read_bytes() == data for path, data in outputs.items())


def test_invalid_transcript_not_cached_and_corrupt_cache_rebuilt(timing_setup):
    p, config, provider, _ = timing_setup
    gen = TimingGenerator(p, config, provider)
    provider.transcript.words[80].start = 0
    with pytest.raises(ValueError, match='timestamps'):
        gen.generate()
    assert not list(gen.root.glob('*.json'))
    provider.transcript = transcript_for(p.approved_script()[0].data)
    gen.generate()
    next(gen.root.glob('*.json')).write_text('{bad JSON')
    gen.generate()
    assert provider.calls == 3


def test_number_and_name_normalization_and_sparse_cues(timing_setup):
    p, config, _, _ = timing_setup
    script = p.approved_script()[0].data.model_copy(deep=True)
    script.scenes[0].narration[0].text = 'Searchbloom scored forty-eight out of fifty. iPullRank scored 45 percent.'
    script.scenes[0].narration[0].company_names = ['Searchbloom', 'iPullRank']
    transcript = transcript_for(script)
    # Give ASR different spacing and number spellings.
    text = transcript.text.replace('Searchbloom', 'Search Bloom').replace('iPullRank', 'i Pull Rank').replace('forty-eight out of fifty', '48 out of 50').replace('45 percent', 'forty-five percent')
    tokens = text.split()
    transcript = Transcript(text=text, duration=2, words=[{'word': w, 'start': n / len(tokens) * 1.9,
                               'end': (n + .8) / len(tokens) * 1.9} for n, w in enumerate(tokens)])
    result = align_script(script, transcript, 2, config, p.config.company_aliases)
    assert result['status'] == 'valid'
    assert result['sentence_count'] == 7
    assert result['scenes'][0]['sentences'][0]['score'] == 1
    assert 1 <= len(result['scenes'][0]['word_cues']) <= 3
    assert {c['kind'] for c in result['scenes'][0]['word_cues']} == {'name', 'quantity'}
    validate_timings(result, script, 2, config)
    assert alignment_text('The SEO Works scored 48/50.', {}) == alignment_text('The SEO Works scored forty-eight out of fifty.', {})


def test_low_match_falls_back_without_regeneration(timing_setup):
    p, config, provider, semantic = timing_setup
    words = provider.transcript.words
    for word in words[:35]:
        word.word = 'unrelated'
    provider.transcript.text = ' '.join(w.word for w in words)
    calls = len(semantic.calls)
    result = TimingGenerator(p, config, provider).generate()
    assert result['status'] == 'review_required'
    scene = result['scenes'][0]
    assert scene['method'] == 'even_fallback' and scene['word_cues'] == []
    assert scene['sentences'][0]['method'] == 'even_fallback'
    assert scene['elements'][0]['start'] == scene['start']
    assert provider.calls == 1 and len(semantic.calls) == calls


def test_wrong_number_is_flagged_despite_high_fuzzy_score(timing_setup):
    p, config, _, _ = timing_setup
    script = p.approved_script()[0].data.model_copy(deep=True)
    script.scenes[0].narration[0].text = 'Acme reports a score of 48 out of 50 according to its measurement process.'
    transcript = transcript_for(script)
    for word in transcript.words:
        if word.word == '48':
            word.word = '49'
    transcript.text = ' '.join(w.word for w in transcript.words)
    result = align_script(script, transcript, 2, config, p.config.company_aliases)
    assert any(i['code'] == 'QUANTITY_MISMATCH' for i in result['issues'])
    assert result['scenes'][0]['method'] == 'even_fallback'


@pytest.mark.parametrize('mutation', ['negative', 'nan', 'overlap', 'outside', 'duration'])
def test_invalid_word_timestamps_rejected(timing_setup, mutation):
    p, _, _, _ = timing_setup
    data = transcript_for(p.approved_script()[0].data).model_dump()
    if mutation == 'duration':
        data['duration'] = 100
    else:
        index = 80 if mutation == 'overlap' else 0
        field, value = {'negative': ('start', -1), 'nan': ('end', float('nan')),
                        'overlap': ('start', 0), 'outside': ('end', 200), 'zero': ('end', 0)}[mutation]
        data['words'][index][field] = value
    with pytest.raises(ValueError):
        validate_transcript(Transcript.model_validate(data), 2)


def test_transcription_sdk_multipart_and_failure_without_retry():
    requests, events = [], []
    def handler(request):
        requests.append(request)
        return httpx.Response(200, json={'text': 'Hello.', 'duration': 1., 'words': [{'word': 'Hello.', 'start': 0., 'end': .9}]},
                              headers={'x-request-id': 'mock-transcript'})
    client = OpenAI(api_key='test', http_client=httpx.Client(transport=httpx.MockTransport(handler)))
    result, run = OpenAITranscriptionProvider(client).transcribe(b'fake-wav', TimingConfig(), lambda event, **kw: events.append((event, kw)))
    body = requests[0].content.decode()
    assert 'name="timestamp_granularities[]"' in body and 'word' in body
    assert 'whisper-1' in body and 'verbose_json' in body and 'fake-wav' in body
    assert 'name="prompt"' not in body
    assert run['usage'] is None and run['request_id'] == 'mock-transcript'
    assert result.words[0].end == .9
    def failure(request):
        requests.append(request)
        return httpx.Response(429, json={'error': {'message': 'private'}})
    client = OpenAI(api_key='secret', http_client=httpx.Client(transport=httpx.MockTransport(failure)))
    with pytest.raises(ValueError, match='no automatic retry'):
        OpenAITranscriptionProvider(client).transcribe(b'private audio', TimingConfig(), lambda event, **kw: events.append((event, kw)))
    assert len(requests) == 2 and 'private' not in json.dumps(events) and 'secret' not in json.dumps(events)


def test_timing_cli_preflight_and_generation(timing_setup, tmp_path, monkeypatch, capsys):
    from article_video.__main__ import main
    from .test_cli import arguments
    p, config, provider, _ = timing_setup
    monkeypatch.setattr('article_video.transcription.OpenAITranscriptionProvider', lambda **kw: provider)
    monkeypatch.setattr('article_video.timing.OpenAITranscriptionProvider', lambda **kw: provider)
    config_path = tmp_path / 'timing.json'
    write_json(config_path, config)
    args = [*arguments(p, tmp_path / 'article.json', tmp_path), 'timing', '--timing-config', str(config_path)]
    assert main([*args, '--check-inputs']) == 0 and provider.calls == 0
    assert main(args) == 0 and provider.calls == 1
    assert 'sentences' in capsys.readouterr().out
    provider.transcript.words[0].word = 'unrelated'
    provider.transcript.text = ' '.join(w.word for w in provider.transcript.words)
    config.min_sentence_score = 1
    write_json(config_path, config)
    assert main([*args, '--force']) == 2


def test_zero_duration_word_is_flagged_and_falls_back(timing_setup):
    p, config, provider, _ = timing_setup
    provider.transcript.words[0].end = provider.transcript.words[0].start
    result = TimingGenerator(p, config, provider).generate()
    assert any(issue['code'] == 'ZERO_DURATION_WORD' for issue in result['issues'])
    assert result['scenes'][0]['method'] == 'even_fallback'
    assert result['scenes'][0]['word_cues'] == []


def test_api_response_capture_and_optional_fields():
    captured = []
    def handler(request):
        return httpx.Response(200, json={'text': 'Hello.', 'duration': 1., 'language': 'english',
                                       'words': [{'word': 'Hello.', 'start': 0., 'end': .9, 'confidence': .9}]})
    client = OpenAI(api_key='test', http_client=httpx.Client(transport=httpx.MockTransport(handler)))
    result, _ = OpenAITranscriptionProvider(client, lambda body, run: captured.append(body)).transcribe(
        b'fake-wav', TimingConfig(), lambda *args, **kw: None)
    assert result.words[0].word == 'Hello.' and captured[0]['words'][0]['confidence'] == .9
    def malformed(request):
        return httpx.Response(200, json={'text': 'Hello.', 'duration': 1., 'words': []})
    client = OpenAI(api_key='test', http_client=httpx.Client(transport=httpx.MockTransport(malformed)))
    with pytest.raises(ValueError):
        OpenAITranscriptionProvider(client, lambda body, run: captured.append(body)).transcribe(
            b'fake-wav', TimingConfig(), lambda *args, **kw: None)
    assert len(captured) == 2 and captured[-1]['words'] == []


def test_small_timestamp_overlap_is_flagged_without_changing_raw_words(timing_setup):
    p, config, provider, _ = timing_setup
    previous = provider.transcript.words[1]
    provider.transcript.words[2].start = previous.start - .001
    original = provider.transcript.model_dump()
    result = TimingGenerator(p, config, provider).generate()
    assert provider.transcript.model_dump() == original
    assert any(issue['code'] == 'OVERLAPPING_WORDS' for issue in result['issues'])
    assert result['scenes'][0]['method'] == 'even_fallback'


def test_retained_response_reused_without_another_request(timing_setup):
    from article_video.audio import audio_hash
    from article_video.storage import digest
    from article_video.timing import TRANSCRIPTION_VERSION
    p, config, provider, _ = timing_setup
    gen = TimingGenerator(p, config, provider)
    audio = (p.output_dir / 'narration.wav').read_bytes()
    key = digest({'version': TRANSCRIPTION_VERSION, 'audio_sha256': audio_hash(audio),
                  'settings': config.request_settings()})
    body = provider.transcript.model_dump(exclude={'omitted_empty_word_count'})
    body['words'].insert(2, {'word': '', 'start': .01, 'end': .02})
    receipt = {'cache_key': key, 'audio_sha256': audio_hash(audio), 'settings': config.request_settings(),
               'body': body, 'body_sha256': digest(body), 'run': {'request_id': 'retained', 'usage': None}}
    response_path = gen.root / 'responses' / f'{key}.json'
    write_json(response_path, receipt)
    provider.fail = True
    result = gen.generate()
    assert provider.calls == 0
    assert any(issue['code'] == 'EMPTY_TRANSCRIPT_WORDS' for issue in result['issues'])
    assert read_json(p.output_dir / 'transcript.json')['data']['omitted_empty_word_count'] == 1
    (gen.root / f'{key}.json').unlink()
    receipt['body']['text'] = 'tampered'
    write_json(response_path, receipt)
    with pytest.raises(ValueError, match='provenance mismatch'):
        gen.generate()
    assert provider.calls == 0


def test_overlap_at_scene_cut_falls_back_on_both_sides(timing_setup):
    p, config, provider, _ = timing_setup
    script = p.approved_script()[0].data
    cut = len(script.scenes[0].narration[0].text.split())
    previous = provider.transcript.words[cut - 1]
    provider.transcript.words[cut].start = previous.end - .001
    result = TimingGenerator(p, config, provider).generate()
    assert [s['method'] for s in result['scenes'][:2]] == ['even_fallback', 'even_fallback']
