"""Stage 8: offline provenance checks and atomic local H.264/AAC export."""
from datetime import datetime, timezone
from fractions import Fraction
import hashlib
import json
import math
from pathlib import Path
import shutil
import subprocess
import tempfile

from .console import render_output
from .storage import digest, read_json, write_json
from .storyboard import (VERSION, VIDEO_ROOT, StoryboardGenerator, StoryboardPlan,
                         TemplateChoice, VisualNode, build_manifest, validate_zod)


def file_hash(path):
    with path.open('rb') as handle:
        return hashlib.file_digest(handle, 'sha256').hexdigest()


def probe_video(path, manifest, scale=1):
    """Reject incomplete, silent-trackless, or incorrectly configured exports."""
    try:
        result = subprocess.run(
            ['ffprobe', '-v', 'error', '-show_streams', '-show_format', '-of', 'json', str(path)],
            capture_output=True, text=True, timeout=30, check=True)
        data = json.loads(result.stdout)
        video, = [s for s in data['streams'] if s['codec_type'] == 'video']
        audio, = [s for s in data['streams'] if s['codec_type'] == 'audio']
        duration = manifest['duration_frames'] / manifest['fps']
        if (video['codec_name'] != 'h264' or video['pix_fmt'] != 'yuv420p'
                or video['width'] != int(manifest['width'] * scale)
                or video['height'] != int(manifest['height'] * scale)
                or Fraction(video['avg_frame_rate']) != manifest['fps']
                or int(video['nb_frames']) != manifest['duration_frames']
                or not math.isfinite(float(video['duration']))
                or abs(float(video['duration']) - duration) > 1 / manifest['fps']
                or audio['codec_name'] != 'aac'
                or not math.isfinite(float(audio['duration']))
                or abs(float(audio['duration']) - duration) > .1
                or 'mp4' not in data['format']['format_name']):
            raise ValueError('Export does not match the H.264/AAC storyboard clock and dimensions')
        return data
    except (OSError, subprocess.SubprocessError, KeyError, TypeError, ZeroDivisionError) as exc:
        raise ValueError('Could not verify MP4; install ffprobe and inspect the render') from exc


class VideoRenderer:
    def __init__(self, pipeline):
        self.pipeline = pipeline

    def preflight(self):
        try:
            return self._preflight()
        except (KeyError, TypeError, IndexError, StopIteration) as exc:
            raise ValueError('Malformed render input; regenerate storyboard from approved inputs') from exc

    def _preflight(self):
        p = self.pipeline
        artifact, timings, claims, snapshot = StoryboardGenerator(p).preflight()
        path = p.output_dir / 'storyboard.json'
        snapshot[path] = file_hash(path)
        manifest = read_json(path)
        validate_zod(manifest)
        expected_inputs = {**p.base_inputs(), 'script': digest(artifact), 'timings': digest(timings),
                           'schema': file_hash(VIDEO_ROOT / 'src/schema.mjs')}
        if (manifest['template_version'] != VERSION
                or any(manifest.get('inputs', {}).get(k) != v for k, v in expected_inputs.items())):
            raise ValueError('Storyboard provenance is stale; regenerate storyboard')
        # Recompile the saved choices, including every diagram excerpt, against
        # current approved copy/evidence and reproducible timing. Zod alone does
        # not prove that a syntactically valid edit is actually source-backed.
        choices = []
        for scene in manifest['scenes']:
            original = next(s for s in artifact.data.scenes if s.scene_id == scene['scene_id'])
            timing = next(s for s in timings['scenes'] if s['scene_id'] == scene['scene_id'])
            nodes = []
            for node in scene['visual_nodes']:
                index = next(i for i, item in enumerate(original.narration)
                             if node['text'] in item.text and node['claim_ids'] == item.claim_ids
                             and any(sentence['narration_index'] == i
                                     and node['text'] in sentence['text']
                                     and max(timing['start_frame'], math.ceil(sentence['start'] * timings['fps']))
                                     == node['start_frame'] for sentence in timing['sentences']))
                nodes.append(VisualNode(text=node['text'], narration_index=index))
            choices.append(TemplateChoice(**{k: scene[k] for k in (
                'scene_id', 'component', 'layout', 'animation', 'theme', 'composition', 'reveal', 'primary_node')},
                visual_nodes=nodes))
        expected = build_manifest(StoryboardPlan(scenes=choices), artifact.data, timings, claims,
                                  p.index, p.config.company_aliases)
        if any(manifest[k] != value for k, value in expected.items()):
            raise ValueError('Storyboard content differs from approved copy, citations or timing')
        source_paths = [*sorted((VIDEO_ROOT / 'src').glob('*')),
                        VIDEO_ROOT / 'scripts/render.mjs', VIDEO_ROOT / 'package.json',
                        VIDEO_ROOT / 'package-lock.json', VIDEO_ROOT / 'tsconfig.json', Path(__file__)]
        for source in source_paths:
            if source.is_file():
                snapshot[source] = file_hash(source)
        return manifest, timings, snapshot

    @staticmethod
    def _unchanged(snapshot):
        if any(not path.exists() or file_hash(path) != value for path, value in snapshot.items()):
            raise ValueError('An input changed during rendering; previous export preserved')

    def render(self, *, preview=False, force=False, concurrency=2, replace_stale=False):
        if not 1 <= concurrency <= 16:
            raise ValueError('Render concurrency must be between 1 and 16')
        manifest, timings, snapshot = self.preflight()
        if shutil.which('ffprobe') is None:
            raise ValueError('Stage 8 requires ffprobe before rendering')
        scale = .5 if preview else 1
        # Remotion mixes to stereo. Duplicating a normalized mono channel adds
        # 3.01 LU; equal-power gain preserves its integrated loudness in stereo.
        channels = read_json(self.pipeline.output_dir / 'narration.json')['audio']['channels']
        narration_volume = 1 / math.sqrt(2) if channels == 1 else 1
        stem = 'video_preview' if preview else 'video'
        output = self.pipeline.output_dir
        target, receipt_path = output / f'{stem}.mp4', output / f'{stem}_render.json'
        inputs = {str(path.resolve()): value for path, value in snapshot.items()}
        settings = {'scale': scale, 'codec': 'h264', 'audio_codec': 'aac',
                    'pixel_format': 'yuv420p', 'crf': 18, 'audio_bitrate': '192k',
                    'concurrency': concurrency, 'narration_volume': narration_volume}
        cache_key = digest({'version': 'render.v2', 'inputs': inputs, 'settings': settings})
        if target.exists() and not force:
            if receipt_path.exists():
                receipt = read_json(receipt_path)
                if receipt.get('cache_key') == cache_key and receipt.get('video_sha256') == file_hash(target):
                    probe_video(target, manifest, scale)
                    self._unchanged(snapshot)
                    return receipt
            if not replace_stale:
                raise ValueError(f'{target} already exists with different inputs; use --force to replace after successful render')
        with tempfile.TemporaryDirectory(prefix=f'.{stem}-', dir=output) as temporary:
            root = Path(temporary).resolve()
            public = root / 'public'
            public.mkdir()
            shutil.copyfile(output / 'narration.wav', public / 'narration.wav')
            if file_hash(public / 'narration.wav') != snapshot[output / 'narration.wav']:
                raise ValueError('Narration changed while staging render')
            rendered = root / 'video.mp4'
            job = root / 'job.json'
            write_json(job, {'manifest': manifest, 'timings': timings, 'public_dir': str(public), 'output': str(rendered),
                             'scale': scale, 'concurrency': concurrency, 'narration_volume': narration_volume})
            try:
                with render_output() as output_options:
                    subprocess.run(['node', 'scripts/render.mjs', str(job)], cwd=VIDEO_ROOT,
                                   check=True, timeout=3600, **output_options)
            except (OSError, subprocess.SubprocessError) as exc:
                raise ValueError('Remotion render failed; previous export preserved. Run npm ci in video/ and inspect worker output') from exc
            probe = probe_video(rendered, manifest, scale)
            self._unchanged(snapshot)
            receipt = {'schema_version': '1.0', 'stage': 'render', 'version': 'render.v2',
                       'cache_key': cache_key, 'inputs': inputs, 'settings': settings,
                       'video_file': target.name, 'video_sha256': file_hash(rendered),
                       'created_at': datetime.now(timezone.utc).isoformat(),
                       'duration_frames': manifest['duration_frames'], 'fps': manifest['fps'],
                       'probe': probe, 'timing_status': timings['status'], 'timing_issues': timings['issues'],
                       'disclosure': 'AI-generated narration.'}
            rendered.replace(target)
            write_json(receipt_path, receipt)
        return receipt
