"""Stage 5: approved narration to cached, loudness-normalized WAV audio."""
from pathlib import Path
import tempfile
from typing import Literal
import uuid

from pydantic import Field
import tiktoken

from .audio import FFmpegNormalizer, audio_hash, canonical_wav, join_wav, wav_info
from .schemas import Model
from .speech import OpenAISpeechProvider
from .storage import digest, read_json, write_bytes, write_json, write_text


class VoiceoverConfig(Model):
    model: str = Field(min_length=1)
    voice: str = Field(min_length=1)
    instructions: str = Field(min_length=1, max_length=4096)
    speed: float = Field(default=1.0, ge=.25, le=4)
    response_format: Literal['wav'] = 'wav'
    max_input_characters: int = Field(default=4096, ge=1, le=4096)
    max_input_tokens: int = Field(default=2000, ge=1, le=2000)
    encoding: str = 'o200k_base'
    token_overhead: int = Field(default=16, ge=0)
    timeout_seconds: float = Field(default=180, gt=0)
    max_retries: int = Field(default=2, ge=0)
    ffmpeg: str = 'ffmpeg'
    ffmpeg_timeout_seconds: float = Field(default=120, gt=0)
    loudness_tolerance_lu: float = Field(default=1.0, gt=0)
    peak_tolerance_db: float = Field(default=.2, ge=0)
    sample_rate: int = Field(default=48000, ge=8000, le=192000)
    channels: Literal[1, 2] = 1
    target_lufs: float = Field(default=-16, ge=-70, le=-5)
    true_peak_db: float = Field(default=-1.5, ge=-9, le=0)
    loudness_range: float = Field(default=11, ge=1, le=50)

    def speech_settings(self):
        return {k: getattr(self, k) for k in ('model', 'voice', 'instructions', 'speed', 'response_format')}

    def normalization_settings(self):
        return {k: getattr(self, k) for k in ('sample_rate', 'channels', 'target_lufs', 'true_peak_db', 'loudness_range', 'loudness_tolerance_lu', 'peak_tolerance_db')}


def narration_chunks(script, config):
    encoding = tiktoken.get_encoding(config.encoding)
    instruction_tokens = len(encoding.encode(config.instructions, disallowed_special=()))
    def fits(text):
        return (len(text) <= config.max_input_characters and
                len(encoding.encode(text, disallowed_special=())) + instruction_tokens + config.token_overhead <= config.max_input_tokens)
    scenes = [' '.join(item.text for item in scene.narration) for scene in script.scenes]
    if not scenes or any(not scene.strip() for scene in scenes):
        raise ValueError('Approved script has empty narration')
    if any(not fits(scene) for scene in scenes):
        raise ValueError('A scene exceeds the configured Speech API input limits; edit and reapprove the script before generation')
    chunks = []
    for scene in scenes:
        if chunks and fits(chunks[-1] + '\n\n' + scene):
            chunks[-1] += '\n\n' + scene
        else:
            chunks.append(scene)
    return chunks


class VoiceoverGenerator:
    def __init__(self, pipeline, config, provider=None, normalizer=None):
        self.pipeline = pipeline
        self.config = config
        self.provider = provider or OpenAISpeechProvider()
        self.normalizer = normalizer
        self.root = pipeline.runner.cache_dir / 'voiceover'
        self.log = pipeline.runner.usage_log

    def _logger(self, operation, key):
        call_id = uuid.uuid4().hex
        def emit(event, **fields):
            self.log.emit(event, stage='voiceover', operation=operation, model=self.config.model,
                          cache_key=key, call_id=call_id, **fields)
        return emit

    def _cached(self, directory, key, emit, force):
        manifest = directory / f'{key}.json'
        audio = directory / f'{key}.wav'
        if force:
            emit('cache_bypass')
            return None
        if manifest.exists() and audio.exists():
            try:
                record = read_json(manifest)
                data = audio.read_bytes()
                if record['cache_key'] != key or audio_hash(data) != record['audio_sha256']:
                    raise ValueError('Cached audio hash mismatch')
                canonical_wav(data)
                emit('cache_hit', usage={})
                return data, record
            except (ValueError, KeyError, OSError):
                emit('cache_invalid')
        emit('cache_miss')
        return None

    def _raw_key(self, text):
        return digest({'version': 'tts.v1', 'text': text, **self.config.speech_settings()})

    def _raw_audio(self, text, force):
        key = self._raw_key(text)
        emit = self._logger('tts', key)
        hit = self._cached(self.root / 'raw', key, emit, force)
        if hit:
            return key, *hit
        try:
            if not getattr(self.provider, 'logs_api_attempts', False):
                emit('provider_attempt_started', input_characters=len(text))
            data, info = self.provider.synthesize(text, self.config, emit)
            data = canonical_wav(data)
            if not getattr(self.provider, 'logs_api_attempts', False):
                emit('provider_attempt_finished', outcome='success', usage=info.get('usage'))
        except Exception as exc:
            if not getattr(self.provider, 'logs_api_attempts', False):
                emit('provider_attempt_finished', outcome='failure', usage=None, error_type=type(exc).__name__)
            emit('generation_failed', error_type=type(exc).__name__)
            raise
        record = {'cache_key': key, 'audio_sha256': audio_hash(data), 'run': info,
                  'text_sha256': digest(text), 'input_characters': len(text), 'audio': wav_info(data)}
        write_bytes(self.root / 'raw' / f'{key}.wav', data)
        write_json(self.root / 'raw' / f'{key}.json', record)
        return key, data, record

    def generate(self, force=False):
        # This checks the complete evidence chain and current approval receipts,
        # including deterministic validation and exact cached semantic verification.
        artifact, approval = self.pipeline.approved_script()
        chunks = narration_chunks(artifact.data, self.config)
        # Preflight FFmpeg before spending on speech; raw WAV survives later local failures.
        normalizer = self.normalizer or FFmpegNormalizer(self.config.ffmpeg, self.config.ffmpeg_timeout_seconds)
        key = digest({'version': 'voiceover.v1', 'raw_keys': [self._raw_key(text) for text in chunks],
                      'normalization': self.config.normalization_settings(), 'ffmpeg_version': normalizer.version})
        emit = self._logger('normalization', key)
        hit = self._cached(self.root, key, emit, force)
        if hit:
            data, record = hit
        else:
            raw = [self._raw_audio(text, force) for text in chunks]
            try:
                with tempfile.TemporaryDirectory() as folder:
                    source, target = Path(folder) / 'joined.wav', Path(folder) / 'normalized.wav'
                    source.write_bytes(join_wav([item[1] for item in raw]))
                    measurements = normalizer.normalize(source, target, self.config)
                    data = canonical_wav(target.read_bytes())
                    info = wav_info(data)
                    if info['sample_rate'] != self.config.sample_rate or info['channels'] != self.config.channels:
                        raise ValueError('Normalized WAV has incorrect sample rate or channels')
                    record = {'cache_key': key, 'audio_sha256': audio_hash(data), 'audio': info,
                              'normalization': measurements, 'ffmpeg_version': normalizer.version,
                              'chunks': [r for _, _, r in raw]}
                write_bytes(self.root / f'{key}.wav', data)
                write_json(self.root / f'{key}.json', record)
                emit('normalization_finished', outcome='success', usage={})
            except Exception as exc:
                emit('normalization_finished', outcome='failure', usage={}, error_type=type(exc).__name__)
                raise
        # Detect concurrent edits/approval changes before publishing, without re-review writes.
        current = read_json(self.pipeline.path('script'))
        receipt = read_json(self.pipeline.output_dir / 'approvals' / 'script.json')
        if digest(current) != digest(artifact) or digest(receipt) != digest(approval):
            raise ValueError('Script or approval changed during voiceover generation; output not replaced')
        metadata = {**record, 'schema_version': '1.0', 'stage': 'voiceover',
                    'inputs': {'script': digest(artifact), 'script_approval': digest(approval)},
                    'text_sha256': digest('\n\n'.join(chunks)), 'config': self.config.model_dump(),
                    'chunks': record['chunks'],
                    'disclosure': 'AI-generated narration.', 'listening_review': 'pending'}
        output = self.pipeline.output_dir
        write_bytes(output / 'narration.wav', data)
        write_text(output / 'narration.txt', '\n\n'.join(chunks) + '\n')
        write_json(output / 'narration.json', metadata)
        return metadata
