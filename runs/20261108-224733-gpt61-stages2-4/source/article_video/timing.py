"""Stage 6: validate approved inputs, transcribe once, then align locally."""
from pathlib import Path
from typing import Literal
import uuid

from pydantic import Field

from .alignment import ALIGNMENT_VERSION, align_script, validate_timings
from .audio import audio_hash, wav_info
from .schemas import Model
from .storage import digest, read_json, write_json, write_text
from .transcription import OpenAITranscriptionProvider, Transcript, parse_response, validate_transcript

TRANSCRIPTION_VERSION = 'transcription.v1'


class TimingConfig(Model):
    model: Literal['whisper-1'] = 'whisper-1'
    language: Literal['en'] = 'en'
    response_format: Literal['verbose_json'] = 'verbose_json'
    timestamp_granularities: list[Literal['word']] = Field(default_factory=lambda: ['word'], min_length=1, max_length=1)
    temperature: Literal[0] = 0
    timeout_seconds: float = Field(default=180, gt=0, allow_inf_nan=False)
    max_audio_bytes: int = Field(default=25000000, ge=1, le=25000000)
    duration_tolerance_seconds: float = Field(default=.35, ge=0, le=1, allow_inf_nan=False)
    fps: int = Field(default=30, ge=1, le=120)
    tail_padding_frames: int = Field(default=6, ge=0, le=120)
    min_sentence_score: float = Field(default=.85, ge=.5, le=1, allow_inf_nan=False)
    max_word_cues_per_scene: int = Field(default=3, ge=1, le=5)

    def request_settings(self):
        return {k: getattr(self, k) for k in ('model', 'language', 'response_format', 'timestamp_granularities', 'temperature')}


def timing_markdown(result):
    lines = ['# Stage 6 timing review', '', f"Status: **{result['status']}**",
             f"Audio: {result['audio_duration_seconds']:.3f}s; {result['fps']} fps; {result['duration_frames']} frames including tail padding.",
             f"Sentences: {result['sentence_count']}; overall normalized similarity: {result['overall_score']:.4f}.",
             '', 'Audio is the master clock. Word cues are approximate (typically 100–300 ms uncertainty).',
             'Fallback spans are estimates, not exact scene durations. Human listening review remains pending.', '',
             '| Scene | Start | End | Frames | Method | Minimum sentence score |',
             '| --- | ---: | ---: | ---: | --- | ---: |']
    for scene in result['scenes']:
        lines.append(f"| {scene['scene_id']} | {scene['start']:.3f} | {scene['end']:.3f} | {scene['duration_frames']} | {scene['method']} | {min(s['score'] for s in scene['sentences']):.4f} |")
    lines += ['', '## Issues', '']
    lines += [f"- {i['code']} — {i['target']}: {i['message']}" for i in result['issues']] or ['No automatic alignment findings.']
    lines += ['', '## Sentence matches', '']
    for scene in result['scenes']:
        for sentence in scene['sentences']:
            lines += [f"- {sentence['sentence_id']} ({sentence['start']:.3f}–{sentence['end']:.3f}s, score {sentence['score']:.4f}, {sentence['method']})",
                      f"  - Approved: {sentence['text']}", f"  - Transcript: {sentence['transcript_text']}"]
    return '\n'.join(lines) + '\n'


class TimingGenerator:
    def __init__(self, pipeline, config, provider=None):
        self.pipeline = pipeline
        self.config = config
        self.provider = provider
        self.root = pipeline.runner.cache_dir / 'timing'

    def preflight(self):
        # No generation/verifier request is permitted in this downstream stage.
        artifact, approval = self.pipeline.approved_script(cache_only=True)
        output = self.pipeline.output_dir
        metadata = read_json(output / 'narration.json')
        audio = (output / 'narration.wav').read_bytes()
        text = '\n\n'.join(' '.join(i.text for i in s.narration) for s in artifact.data.scenes)
        inputs = {'script': digest(artifact), 'script_approval': digest(approval)}
        if metadata.get('stage') != 'voiceover' or metadata.get('inputs') != inputs:
            raise ValueError('Narration is not bound to the current approved script')
        if metadata.get('text_sha256') != digest(text) or (output / 'narration.txt').read_text() != text + '\n':
            raise ValueError('Narration text differs from the approved script')
        if metadata.get('audio_sha256') != audio_hash(audio) or metadata.get('audio') != wav_info(audio):
            raise ValueError('Narration WAV hash or metadata mismatch')
        if len(audio) > self.config.max_audio_bytes:
            raise ValueError('Narration exceeds transcription upload limit; no request sent')
        # Snapshot all approval/evidence inputs for concurrent-edit detection.
        names = ['article.json', 'selection.json', 'facts.json', 'scenes.json',
                 'selection_review.json', 'facts_review.json', 'script_review.json',
                 'approvals/selection.json', 'approvals/facts.json', 'approvals/script.json',
                 'narration.json', 'narration.txt', 'narration.wav']
        paths = [self.pipeline.article_path, *[output / name for name in names if (output / name).exists()]]
        snapshot = {path: audio_hash(path.read_bytes()) for path in paths}
        return artifact, {**inputs, 'narration_metadata': digest(metadata), 'audio_sha256': audio_hash(audio)}, audio, metadata['audio'], snapshot

    def _transcribe(self, audio, duration, force):
        key = digest({'version': TRANSCRIPTION_VERSION, 'audio_sha256': audio_hash(audio),
                      'settings': self.config.request_settings()})
        call_id = uuid.uuid4().hex
        def emit(event, **fields):
            self.pipeline.runner.usage_log.emit(event, stage='timing', operation='transcription',
                                               model=self.config.model, cache_key=key, call_id=call_id, **fields)
        path = self.root / f'{key}.json'
        response_path = self.root / 'responses' / f'{key}.json'
        if path.exists() and not force:
            try:
                record = read_json(path)
                transcript = Transcript.model_validate(record['data'])
                if record['cache_key'] != key or record['data_sha256'] != digest(transcript):
                    raise ValueError('Transcript cache hash mismatch')
                validate_transcript(transcript, duration, self.config.duration_tolerance_seconds)
                emit('cache_hit', usage={})
                return transcript, record
            except (ValueError, KeyError, TypeError, OSError):
                emit('cache_invalid')
        emit('cache_bypass' if force else 'cache_miss')
        def capture(body, run):
            # Diagnostic receipt, not a successful transcript cache. Never logs
            # source text and survives local schema/alignment errors.
            write_json(self.root / 'responses' / f'{key}.json', {
                'cache_key': key, 'audio_sha256': audio_hash(audio),
                'settings': self.config.request_settings(), 'body_sha256': digest(body), 'body': body, 'run': run})
        provider = self.provider or OpenAITranscriptionProvider(capture_response=capture)
        external = getattr(provider, 'logs_api_attempts', False)
        try:
            if response_path.exists() and not force:
                receipt = read_json(response_path)
                if (receipt['cache_key'] != key or receipt['audio_sha256'] != audio_hash(audio)
                        or receipt['settings'] != self.config.request_settings()
                        or receipt['body_sha256'] != digest(receipt['body'])):
                    raise ValueError('Retained transcription response provenance mismatch; no new request sent')
                transcript, run = parse_response(receipt['body']), receipt['run']
                emit('response_reused', usage={})
            else:
                if not external:
                    emit('provider_attempt_started')
                transcript, run = provider.transcribe(audio, self.config, emit)
                if not external:
                    emit('provider_attempt_finished', outcome='success', usage=run.get('usage'))
            validate_transcript(transcript, duration, self.config.duration_tolerance_seconds)
        except Exception as exc:
            emit('generation_failed', error_type=type(exc).__name__)
            raise
        record = {'schema_version': '1.0', 'stage': 'transcription', 'cache_key': key,
                  'version': TRANSCRIPTION_VERSION, 'audio_sha256': audio_hash(audio),
                  'settings': self.config.request_settings(), 'run': run,
                  'data_sha256': digest(transcript), 'data': transcript.model_dump()}
        write_json(path, record)
        return transcript, record

    def generate(self, force=False):
        artifact, inputs, audio, info, snapshot = self.preflight()
        transcript, record = self._transcribe(audio, info['duration_seconds'], force)
        result = align_script(artifact.data, transcript, info['duration_seconds'], self.config,
                              self.pipeline.config.company_aliases)
        validate_timings(result, artifact.data, info['duration_seconds'], self.config)
        result.update(schema_version='1.0', stage='timing', inputs=inputs,
                      alignment_version=ALIGNMENT_VERSION, config=self.config.model_dump(),
                      transcript_sha256=digest(record), transcription_cache_key=record['cache_key'],
                      listening_review='pending')
        result['cache_key'] = digest({'inputs': inputs, 'transcript': digest(record),
                                      'version': ALIGNMENT_VERSION, 'config': self.config.model_dump(),
                                      'aliases': self.pipeline.config.company_aliases})
        if any(not path.exists() or audio_hash(path.read_bytes()) != value for path, value in snapshot.items()):
            raise ValueError('An approved input changed during timing; output not replaced')
        output = self.pipeline.output_dir
        write_json(output / 'transcript.json', record)
        write_json(output / 'timings.json', result)
        write_text(output / 'timing_review.md', timing_markdown(result))
        return result
