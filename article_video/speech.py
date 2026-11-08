"""Speech API adapter with visible attempts and binary-response usage semantics."""
import os
import time

from openai import APIConnectionError, APIError, OpenAI

from .audio import canonical_wav
from .llm import GenerationError


class OpenAISpeechProvider:
    logs_api_attempts = True

    def __init__(self, client=None):
        self.client = client

    def synthesize(self, text, config, log):
        if self.client is None:
            if not os.environ.get('OPENAI_API_KEY'):
                raise GenerationError('OPENAI_API_KEY is required for uncached voiceover generation')
            self.client = OpenAI(timeout=config.timeout_seconds, max_retries=0)
        client = self.client.with_options(max_retries=0, timeout=config.timeout_seconds)
        for attempt in range(1, config.max_retries + 2):
            log('api_attempt_started', api_attempt=attempt, input_characters=len(text))
            status = request_id = usage = None
            try:
                response = client.audio.speech.with_raw_response.create(
                    model=config.model, voice=config.voice, input=text, instructions=config.instructions,
                    speed=config.speed, response_format=config.response_format,
                )
                status = response.status_code
                request_id = response.headers.get('x-request-id')
                data = canonical_wav(response.http_response.content)
            except Exception as exc:
                retryable = False
                delay = 2 ** (attempt - 1)
                if isinstance(exc, APIError):
                    status = getattr(exc, 'status_code', None)
                    request_id = getattr(exc, 'request_id', None)
                    retryable = isinstance(exc, APIConnectionError) or (status is not None and (status in {408, 409, 429} or status >= 500))
                    http_response = getattr(exc, 'response', None)
                    if http_response is not None:
                        header = http_response.headers.get('x-should-retry')
                        if header is not None:
                            retryable = header == 'true'
                        try:
                            usage = http_response.json().get('usage')
                        except (ValueError, AttributeError):
                            pass
                        try:
                            seconds = float(http_response.headers.get('retry-after-ms', 'nan')) / 1000
                            if not 0 < seconds <= 60:
                                seconds = float(http_response.headers.get('retry-after', 'nan'))
                            if 0 < seconds <= 60:
                                delay = seconds
                        except ValueError:
                            pass
                retrying = retryable and attempt <= config.max_retries
                log('api_attempt_finished', api_attempt=attempt, outcome='failure', http_status=status,
                    request_id=request_id, usage=usage, retrying=retrying, error_type=type(exc).__name__)
                if retrying:
                    time.sleep(delay)
                    continue
                raise GenerationError(f'Speech generation failed ({type(exc).__name__}, HTTP {status or "n/a"})') from None
            # Binary WAV responses do not expose token usage or a resolved model ID.
            log('api_attempt_finished', api_attempt=attempt, outcome='success', http_status=status,
                request_id=request_id, usage=None, retrying=False, audio_bytes=len(data))
            return data, {'requested_model': config.model, 'resolved_model': None,
                          'request_id': request_id, 'usage': None}
