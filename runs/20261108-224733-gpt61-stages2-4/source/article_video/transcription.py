"""One-shot Whisper adapter; no hidden SDK retries or script prompting."""
import math
import os

from openai import APIError, OpenAI
from pydantic import Field

from .llm import GenerationError
from .schemas import Model

WORD_JITTER_TOLERANCE_SECONDS = .3

class Word(Model):
    word: str = Field(min_length=1)
    start: float = Field(ge=0, allow_inf_nan=False)
    end: float = Field(ge=0, allow_inf_nan=False)


class Transcript(Model):
    text: str = Field(min_length=1)
    duration: float = Field(gt=0, allow_inf_nan=False)
    words: list[Word] = Field(min_length=1)
    omitted_empty_word_count: int = Field(default=0, ge=0)


def validate_transcript(transcript, audio_duration, tolerance=.35):
    if not math.isfinite(audio_duration) or audio_duration <= 0:
        raise ValueError('Invalid audio duration')
    if abs(transcript.duration - audio_duration) > tolerance:
        raise ValueError('Transcript duration differs from master WAV duration')
    previous_start = previous_end = 0
    for word in transcript.words:
        if (word.end < word.start or word.start + WORD_JITTER_TOLERANCE_SECONDS < previous_start
                or word.end + WORD_JITTER_TOLERANCE_SECONDS < previous_end or word.end > audio_duration):
            raise ValueError('Word timestamps have invalid bounds or exceed the 300 ms ordering tolerance')
        previous_start, previous_end = word.start, word.end


def parse_response(body):
    # The API may add optional fields. Retain its full response separately, while
    # validating only the documented fields this stage consumes.
    return Transcript.model_validate({
        'text': body['text'], 'duration': body['duration'],
        'words': [{k: word[k] for k in ('word', 'start', 'end')}
                  for word in body['words'] if word['word'].strip()],
        'omitted_empty_word_count': sum(not word['word'].strip() for word in body['words']),
    })


class OpenAITranscriptionProvider:
    logs_api_attempts = True

    def __init__(self, client=None, capture_response=None):
        self.client = client
        self.capture_response = capture_response

    def transcribe(self, audio, config, log):
        if self.client is None:
            if not os.environ.get('OPENAI_API_KEY'):
                raise GenerationError('OPENAI_API_KEY is required for uncached transcription')
            self.client = OpenAI(timeout=config.timeout_seconds, max_retries=0)
        client = self.client.with_options(timeout=config.timeout_seconds, max_retries=0)
        log('api_attempt_started', api_attempt=1, audio_bytes=len(audio))
        status = request_id = usage = None
        try:
            raw = client.audio.transcriptions.with_raw_response.create(
                file=('narration.wav', audio, 'audio/wav'), **config.request_settings(),
            )
            status = raw.status_code
            request_id = raw.headers.get('x-request-id')
            body = raw.http_response.json()
            usage = body.get('usage')
            if self.capture_response:
                self.capture_response(body, {'requested_model': config.model, 'resolved_model': None,
                                             'request_id': request_id, 'usage': usage})
            result = parse_response(body)
        except Exception as exc:
            if isinstance(exc, APIError):
                status = getattr(exc, 'status_code', status)
                request_id = getattr(exc, 'request_id', request_id)
            log('api_attempt_finished', api_attempt=1, outcome='failure', http_status=status,
                request_id=request_id, usage=usage, retrying=False, error_type=type(exc).__name__)
            raise GenerationError(f'Transcription failed ({type(exc).__name__}, HTTP {status or "n/a"}); no automatic retry') from None
        log('api_attempt_finished', api_attempt=1, outcome='success', http_status=status,
            request_id=request_id, usage=usage, retrying=False)
        return result, {'requested_model': config.model, 'resolved_model': None,
                        'request_id': request_id, 'usage': usage}
