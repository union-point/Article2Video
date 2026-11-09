"""Stage 5 tests: synthetic PCM audio and mocked HTTP, never paid speech."""
import io
import json
import math
from pathlib import Path
import shutil
import struct
import wave

import httpx
from openai import OpenAI
import pytest

from article_video.audio import AudioError, FFmpegNormalizer, canonical_wav, wav_info
from article_video.pipeline import ReviewRequired
from article_video.speech import OpenAISpeechProvider
from article_video.storage import digest, read_json, write_json
from article_video.voiceover import VoiceoverConfig, VoiceoverGenerator, narration_chunks


def tone(seconds=2, sample_rate=48000):
    output = io.BytesIO()
    with wave.open(output, 'wb') as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(sample_rate)
        audio.writeframes(b''.join(struct.pack('<h', int(2200 * math.sin(2 * math.pi * 440 * n / sample_rate)))
                                   for n in range(int(seconds * sample_rate))))
    return output.getvalue()


class FakeSpeech:
    def __init__(self):
        self.calls = []
        self.fail = False

    def synthesize(self, text, config, log):
        self.calls.append((text, config.speech_settings()))
        if self.fail:
            raise ValueError('Synthetic speech failure')
        return tone(), {'requested_model': config.model, 'resolved_model': None, 'request_id': 'mock', 'usage': None}


class FakeNormalizer:
    version = 'mock-ffmpeg-v1'

    def __init__(self):
        self.calls = 0
        self.fail = False

    def normalize(self, source, target, config):
        self.calls += 1
        if self.fail:
            raise AudioError('Synthetic normalization failure')
        target.write_bytes(source.read_bytes())
        return {'input': {'input_i': '-23'}, 'output': {'input_i': str(config.target_lufs)}}


@pytest.fixture
def setup_voiceover(setup_pipeline):
    p, _ = setup_pipeline
    p.run(auto_approve=True)
    config = VoiceoverConfig.model_validate(read_json(Path(__file__).resolve().parents[2] / 'configs' / 'voiceover_config.json'))
    speech, normalizer = FakeSpeech(), FakeNormalizer()
    return p, config, speech, normalizer


def test_continuous_approved_narration_settings_and_preservation(setup_voiceover):
    p, config, speech, normalizer = setup_voiceover
    before = {f: f.read_bytes() for f in p.output_dir.rglob('*') if f.is_file()}
    result = VoiceoverGenerator(p, config, speech, normalizer).generate()
    script = read_json(p.path('script'))['data']
    expected = '\n\n'.join(' '.join(i['text'] for i in scene['narration']) for scene in script['scenes'])
    assert speech.calls == [(expected, config.speech_settings())]
    assert config.voice == 'alloy' and config.speed == 1.0
    assert result['config']['instructions'] == config.instructions
    assert result['text_sha256'] == digest(expected)
    assert result['audio']['sample_rate'] == 48000
    assert all(f.read_bytes() == content for f, content in before.items())
    assert result['inputs']['script'] == digest(read_json(p.path('script')))
    assert 'listening_review' not in result


def test_final_cache_hit_needs_no_raw_cache_or_speech_request(setup_voiceover):
    p, config, speech, normalizer = setup_voiceover
    gen = VoiceoverGenerator(p, config, speech, normalizer)
    first = gen.generate()
    shutil.rmtree(gen.root / 'raw')
    assert gen.generate() == first
    assert len(speech.calls) == 1 and normalizer.calls == 1
    events = [json.loads(line) for line in p.runner.usage_log.path.read_text().splitlines()]
    assert any(e['stage'] == 'voiceover' and e['event'] == 'cache_hit' and e['usage'] == {} for e in events)


@pytest.mark.parametrize('field,value', [('voice', 'coral'), ('speed', .95), ('instructions', 'Different instructions.'), ('model', 'gpt-4o-mini-tts')])
def test_speech_settings_are_in_audio_cache_key(setup_voiceover, field, value):
    p, config, speech, normalizer = setup_voiceover
    VoiceoverGenerator(p, config, speech, normalizer).generate()
    setattr(config, field, value)
    VoiceoverGenerator(p, config, speech, normalizer).generate()
    assert len(speech.calls) == 2


def test_normalization_only_changes_reuse_paid_audio(setup_voiceover):
    p, config, speech, normalizer = setup_voiceover
    first = VoiceoverGenerator(p, config, speech, normalizer).generate()
    config.target_lufs = -18
    second = VoiceoverGenerator(p, config, speech, normalizer).generate()
    assert len(speech.calls) == 1 and normalizer.calls == 2
    assert first['cache_key'] != second['cache_key']


def test_force_regenerates_and_failure_does_not_replace_output(setup_voiceover):
    p, config, speech, normalizer = setup_voiceover
    gen = VoiceoverGenerator(p, config, speech, normalizer)
    gen.generate()
    gen.generate(force=True)
    assert len(speech.calls) == 2 and normalizer.calls == 2
    before = {f: f.read_bytes() for f in p.output_dir.glob('narration.*')}
    speech.fail = True
    with pytest.raises(ValueError):
        gen.generate(force=True)
    assert all(f.read_bytes() == content for f, content in before.items())


def test_local_failure_keeps_raw_cache_for_retry(setup_voiceover):
    p, config, speech, normalizer = setup_voiceover
    normalizer.fail = True
    gen = VoiceoverGenerator(p, config, speech, normalizer)
    with pytest.raises(AudioError):
        gen.generate()
    assert not (p.output_dir / 'narration.wav').exists()
    normalizer.fail = False
    gen.generate()
    assert len(speech.calls) == 1


def test_missing_or_stale_approval_blocks_speech(setup_voiceover):
    p, config, speech, normalizer = setup_voiceover
    receipt = p.output_dir / 'approvals/script.json'
    receipt.unlink()
    with pytest.raises(ReviewRequired):
        VoiceoverGenerator(p, config, speech, normalizer).generate()
    assert not speech.calls


def test_scene_boundary_fallback_and_oversized_scene_preflight(setup_voiceover):
    p, config, speech, normalizer = setup_voiceover
    script = p.approved_script()[0].data
    scene_texts = [' '.join(i.text for i in scene.narration) for scene in script.scenes]
    config.max_input_characters = max(map(len, scene_texts))
    chunks = narration_chunks(script, config)
    assert len(chunks) == 6
    assert '\n\n'.join(chunks) == '\n\n'.join(scene_texts)
    result = VoiceoverGenerator(p, config, speech, normalizer).generate()
    assert len(result['chunks']) == 6
    # Distinct scene text needs one request per segment, then reuses the cache.
    assert len(speech.calls) == 6
    VoiceoverGenerator(p, config, speech, normalizer).generate()
    assert len(speech.calls) == 6
    assert all(settings == config.speech_settings() for _, settings in speech.calls)
    config.max_input_characters = 10
    with pytest.raises(ValueError, match='scene exceeds'):
        VoiceoverGenerator(p, config, speech, normalizer).generate(force=True)
    assert len(speech.calls) == 6


def test_token_limit_includes_instructions(setup_voiceover):
    p, config, _, _ = setup_voiceover
    config.max_input_tokens = 5
    with pytest.raises(ValueError, match='scene exceeds'):
        narration_chunks(p.approved_script()[0].data, config)


def test_repeated_scene_reuses_paid_speech_without_editorial_gate(setup_voiceover):
    p, config, speech, normalizer = setup_voiceover
    data = read_json(p.path('script'))
    scenes = data['data']['scenes']
    scenes[1]['narration'][0]['text'] = scenes[0]['narration'][0]['text']
    write_json(p.path('script'), data)
    _, report = p.review('script')
    assert not report.flags
    p.auto_approve('script')
    config.max_input_characters = max(len(s['narration'][0]['text']) for s in scenes)
    result = VoiceoverGenerator(p, config, speech, normalizer).generate()
    assert len(result['chunks']) == 6
    assert len(speech.calls) == 5


def test_corrupt_normalized_cache_rebuilds_without_speech(setup_voiceover):
    p, config, speech, normalizer = setup_voiceover
    gen = VoiceoverGenerator(p, config, speech, normalizer)
    result = gen.generate()
    (gen.root / f"{result['cache_key']}.wav").write_bytes(b'corrupt')
    gen.generate()
    assert len(speech.calls) == 1 and normalizer.calls == 2


def test_concurrent_script_edit_prevents_publish(setup_voiceover):
    p, config, speech, normalizer = setup_voiceover
    original = normalizer.normalize
    def edit(source, target, cfg):
        result = original(source, target, cfg)
        document = read_json(p.path('script'))
        document['data']['title']['text'] = 'Edited'
        write_json(p.path('script'), document)
        return result
    normalizer.normalize = edit
    with pytest.raises(ValueError, match='changed during'):
        VoiceoverGenerator(p, config, speech, normalizer).generate()
    assert not (p.output_dir / 'narration.wav').exists()


def test_ffmpeg_normalization_on_synthetic_audio(tmp_path):
    if not shutil.which('ffmpeg'):
        pytest.skip('FFmpeg not installed')
    config = VoiceoverConfig.model_validate(read_json(Path(__file__).resolve().parents[2] / 'configs' / 'voiceover_config.json'))
    source, target = tmp_path / 'raw.wav', tmp_path / 'normal.wav'
    source.write_bytes(tone(seconds=4))
    measurements = FFmpegNormalizer().normalize(source, target, config)
    assert abs(float(measurements['output']['input_i']) - config.target_lufs) < 1
    assert wav_info(target.read_bytes())['sample_rate'] == config.sample_rate
    assert abs(wav_info(target.read_bytes())['duration_seconds'] - 4) < .05


def test_speech_sdk_wire_format_and_unknown_usage(tmp_path):
    requests = []
    def handler(request):
        requests.append(json.loads(request.content))
        return httpx.Response(200, content=tone(), headers={'content-type': 'audio/wav', 'x-request-id': 'mock-request'})
    client = OpenAI(api_key='mock-test-key', http_client=httpx.Client(transport=httpx.MockTransport(handler)))
    config = VoiceoverConfig.model_validate(read_json(Path(__file__).resolve().parents[2] / 'configs' / 'voiceover_config.json'))
    events = []
    data, info = OpenAISpeechProvider(client).synthesize('An approved excerpt.', config, lambda event, **fields: events.append((event, fields)))
    assert wav_info(data)['duration_seconds'] == 2
    assert requests[0] == {**config.speech_settings(), 'input': 'An approved excerpt.'}
    assert info['usage'] is None
    assert events[-1][1]['usage'] is None and events[-1][1]['request_id'] == 'mock-request'


def test_speech_retries_and_failures_logged_without_secrets(monkeypatch):
    calls, events = [], []
    def handler(request):
        calls.append(request)
        if len(calls) == 1:
            raise httpx.ConnectError('secret body', request=request)
        return httpx.Response(429, json={'error': {'message': 'secret body'}})
    monkeypatch.setattr('article_video.speech.time.sleep', lambda seconds: None)
    client = OpenAI(api_key='secret-key', http_client=httpx.Client(transport=httpx.MockTransport(handler)))
    config = VoiceoverConfig.model_validate(read_json(Path(__file__).resolve().parents[2] / 'configs' / 'voiceover_config.json'))
    with pytest.raises(ValueError):
        OpenAISpeechProvider(client).synthesize('Private script', config, lambda event, **fields: events.append((event, fields)))
    assert len(calls) == 3
    finished = [f for e, f in events if e == 'api_attempt_finished']
    assert [f['retrying'] for f in finished] == [True, True, False]
    assert 'secret' not in json.dumps(events) and 'Private script' not in json.dumps(events)


@pytest.mark.parametrize('data', [b'', b'not audio', b'RIFFbadWAVE'])
def test_invalid_audio_rejected(data):
    with pytest.raises(AudioError):
        canonical_wav(data)


def test_unknown_length_streaming_wav_header_is_canonicalized():
    data = bytearray(tone())
    data[4:8] = b'\xff' * 4
    data[40:44] = b'\xff' * 4
    assert wav_info(canonical_wav(bytes(data)))['duration_seconds'] == 2


def test_stale_script_approval_blocks_speech(setup_voiceover):
    p, config, speech, normalizer = setup_voiceover
    raw = read_json(p.path('script'))
    raw['data']['title']['text'] = 'Acme review process'
    write_json(p.path('script'), raw)
    with pytest.raises(ReviewRequired, match='stale'):
        VoiceoverGenerator(p, config, speech, normalizer).generate()
    assert not speech.calls


def test_missing_ffmpeg_fails_before_speech(setup_voiceover):
    p, config, speech, _ = setup_voiceover
    config.ffmpeg = '/nonexistent/stage5-ffmpeg'
    with pytest.raises(AudioError, match='FFmpeg is required'):
        VoiceoverGenerator(p, config, speech).generate()
    assert not speech.calls


def test_malformed_api_audio_is_logged_and_not_cached():
    events, calls = [], []
    def handler(request):
        calls.append(request)
        return httpx.Response(200, content=b'not WAV', headers={'x-request-id': 'bad-audio'})
    client = OpenAI(api_key='mock', http_client=httpx.Client(transport=httpx.MockTransport(handler)))
    config = VoiceoverConfig.model_validate(read_json(Path(__file__).resolve().parents[2] / 'configs' / 'voiceover_config.json'))
    with pytest.raises(ValueError, match='Speech generation failed'):
        OpenAISpeechProvider(client).synthesize('Test', config, lambda event, **fields: events.append((event, fields)))
    assert len(calls) == 1
    assert events[-1][1]['outcome'] == 'failure'
    assert events[-1][1]['http_status'] == 200


def test_voiceover_cli_with_mocked_speech(setup_voiceover, tmp_path, monkeypatch, capsys):
    from article_video.__main__ import main
    from .test_cli import arguments
    p, config, speech, normalizer = setup_voiceover
    monkeypatch.setattr('article_video.voiceover.OpenAISpeechProvider', lambda: speech)
    monkeypatch.setattr('article_video.voiceover.FFmpegNormalizer', lambda *args: normalizer)
    config_path = tmp_path / 'voiceover.json'
    write_json(config_path, config)
    args = arguments(p, tmp_path / 'article.json', tmp_path)
    assert main([*args, 'voiceover', '--voiceover-config', str(config_path)]) == 0
    assert 'listening review is optional' in capsys.readouterr().out
    assert (p.output_dir / 'narration.wav').exists()
    assert len(speech.calls) == 1
