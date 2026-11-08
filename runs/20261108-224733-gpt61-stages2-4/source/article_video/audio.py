"""Local WAV validation, joining, and two-pass FFmpeg loudness normalization."""
import hashlib
import io
import json
import math
from pathlib import Path
import shutil
import subprocess
import wave


class AudioError(ValueError):
    pass


def audio_hash(data: bytes):
    return hashlib.sha256(data).hexdigest()


def canonical_wav(data: bytes) -> bytes:
    """Validate PCM audio, accepting the unknown-length header used by streaming WAV."""
    try:
        with wave.open(io.BytesIO(data), 'rb') as source:
            params = source.getparams()
            if params.comptype != 'NONE' or params.sampwidth != 2 or params.nchannels not in {1, 2}:
                raise AudioError('TTS must return mono/stereo 16-bit PCM WAV')
            frames = source.readframes(params.nframes)
            frame_size = params.sampwidth * params.nchannels
            if not frames or len(frames) % frame_size or not any(frames):
                raise AudioError('Empty, silent, or malformed WAV audio')
            if data[4:8] != b'\xff' * 4 and len(frames) != params.nframes * frame_size:
                raise AudioError('Truncated WAV audio')
        result = io.BytesIO()
        with wave.open(result, 'wb') as target:
            target.setparams(params._replace(nframes=len(frames) // frame_size))
            target.writeframes(frames)
        return result.getvalue()
    except (wave.Error, EOFError) as exc:
        raise AudioError('Invalid WAV audio') from exc


def wav_info(data: bytes):
    data = canonical_wav(data)
    with wave.open(io.BytesIO(data), 'rb') as source:
        return {'duration_seconds': source.getnframes() / source.getframerate(),
                'sample_rate': source.getframerate(), 'channels': source.getnchannels(),
                'sample_width_bytes': source.getsampwidth(), 'frames': source.getnframes()}


def join_wav(parts: list[bytes]) -> bytes:
    result = io.BytesIO()
    expected = None
    with wave.open(result, 'wb') as target:
        for data in parts:
            with wave.open(io.BytesIO(canonical_wav(data)), 'rb') as source:
                params = (source.getnchannels(), source.getsampwidth(), source.getframerate())
                if expected is None:
                    expected = params
                    target.setnchannels(params[0])
                    target.setsampwidth(params[1])
                    target.setframerate(params[2])
                if params != expected:
                    raise AudioError('TTS chunks have incompatible WAV formats')
                target.writeframes(source.readframes(source.getnframes()))
    return result.getvalue()


class FFmpegNormalizer:
    def __init__(self, executable='ffmpeg', timeout_seconds=120):
        self.timeout_seconds = timeout_seconds
        self.executable = shutil.which(executable)
        if self.executable is None:
            raise AudioError('FFmpeg is required for Stage 5; install it before generating speech')
        self.version = self._run(['-version']).stdout.splitlines()[0].strip()
        if 'loudnorm' not in self._run(['-hide_banner', '-filters']).stdout:
            raise AudioError('FFmpeg does not have the loudnorm filter')

    def _run(self, args):
        try:
            result = subprocess.run([self.executable, '-nostdin', *args], capture_output=True,
                                    text=True, timeout=self.timeout_seconds)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise AudioError('FFmpeg execution failed') from exc
        if result.returncode:
            raise AudioError('FFmpeg could not process the WAV audio')
        return result

    @staticmethod
    def measurement(stderr):
        try:
            return json.loads(stderr[stderr.rfind('{'):stderr.rfind('}') + 1])
        except (ValueError, KeyError) as exc:
            raise AudioError('FFmpeg returned no loudness measurement') from exc

    def normalize(self, source: Path, target: Path, config):
        settings = f'I={config.target_lufs}:TP={config.true_peak_db}:LRA={config.loudness_range}'
        measured = self.measurement(self._run([
            '-hide_banner', '-i', str(source), '-af', f'loudnorm={settings}:print_format=json',
            '-f', 'null', '-',
        ]).stderr)
        if any(not math.isfinite(float(measured[k])) for k in ('input_i', 'input_tp', 'input_lra', 'input_thresh', 'target_offset')):
            raise AudioError('Audio loudness could not be measured')
        calibration = ':'.join(f'{name}={measured[key]}' for name, key in [
            ('measured_I', 'input_i'), ('measured_TP', 'input_tp'), ('measured_LRA', 'input_lra'),
            ('measured_thresh', 'input_thresh'), ('offset', 'target_offset')])
        self._run(['-hide_banner', '-y', '-i', str(source), '-af',
                   f'loudnorm={settings}:{calibration}:linear=true', '-ar', str(config.sample_rate),
                   '-ac', str(config.channels), '-c:a', 'pcm_s16le', str(target)])
        final = self.measurement(self._run([
            '-hide_banner', '-i', str(target), '-af', f'loudnorm={settings}:print_format=json',
            '-f', 'null', '-',
        ]).stderr)
        if abs(float(final['input_i']) - config.target_lufs) > config.loudness_tolerance_lu:
            raise AudioError('Normalized audio is outside the loudness tolerance')
        if float(final['input_tp']) > config.true_peak_db + config.peak_tolerance_db:
            raise AudioError('Normalized audio exceeds the true-peak ceiling')
        return {'input': measured, 'output': final}
