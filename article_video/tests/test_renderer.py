"""Render trust boundary, failure-safe publication, and media contract."""
import copy
import json
import math
import subprocess

import pytest

from article_video import renderer
from article_video.renderer import VideoRenderer, probe_video
from article_video.storage import read_json, write_json
from article_video.storyboard import StoryboardGenerator
from .test_storyboard import storyboard_setup  # noqa: F401
from .test_timing import timing_setup  # noqa: F401


@pytest.fixture
def render_setup(storyboard_setup, monkeypatch):
    p, planner, semantic = storyboard_setup
    StoryboardGenerator(p).generate()
    calls = []
    original_run = subprocess.run

    def worker(args, **kwargs):
        if args[:2] != ['node', 'scripts/render.mjs']:
            return original_run(args, **kwargs)
        job = read_json(renderer.Path(args[2]))
        calls.append(job)
        renderer.Path(job['output']).write_bytes(b'mocked mp4')
        return subprocess.CompletedProcess(args, 0)

    monkeypatch.setattr(renderer.subprocess, 'run', worker)
    monkeypatch.setattr(renderer, 'probe_video', lambda *args: {'checked': True})
    return p, VideoRenderer(p), calls, planner, semantic


def test_export_cache_preview_and_upstream_preservation(render_setup):
    p, gen, calls, planner, semantic = render_setup
    before = {f: f.read_bytes() for f in p.output_dir.rglob('*') if f.is_file()}
    api_calls = planner.calls, len(semantic.calls)
    result = gen.render()
    assert result['video_file'] == 'video.mp4'
    assert result['duration_frames'] == 66
    assert result['settings']['narration_volume'] == 1 / math.sqrt(2)
    assert calls[0]['narration_volume'] == 1 / math.sqrt(2)
    assert 'final_approval' not in result and 'visual_review' not in result
    assert gen.render() == result and len(calls) == 1
    preview = gen.render(preview=True)
    assert preview['settings']['scale'] == .5 and preview['video_file'] == 'video_preview.mp4'
    assert calls[0]['manifest'] == calls[1]['manifest']
    assert not renderer.Path(calls[0]['public_dir']).exists()
    assert all(f.read_bytes() == content for f, content in before.items())
    assert (planner.calls, len(semantic.calls)) == api_calls


@pytest.mark.parametrize('change', ['copy', 'citation', 'cue', 'node', 'provenance', 'audio', 'approval'])
def test_stale_or_edited_inputs_stop_before_render(render_setup, change):
    p, gen, calls, _, _ = render_setup
    path = p.output_dir / 'storyboard.json'
    manifest = read_json(path)
    scene = manifest['scenes'][0]
    if change == 'copy':
        scene['elements'][0]['text'] = 'Invented title'
    elif change == 'citation':
        scene['elements'][0]['source_ids'] = ['invented.source']
    elif change == 'cue':
        scene['elements'][1]['start_frame'] += 1
    elif change == 'node':
        scene['visual_nodes'] = [{'element_id': 'scene_001.node_0', 'role': 'body',
            'text': 'Invented excerpt', 'claim_ids': scene['elements'][0]['claim_ids'],
            'source_ids': scene['elements'][0]['source_ids'], 'start_frame': 0,
            'end_frame': scene['duration_frames']}]
    elif change == 'provenance':
        manifest['inputs']['script'] = 'stale'
    elif change == 'audio':
        (p.output_dir / 'narration.wav').write_bytes(b'changed')
    else:
        (p.output_dir / 'approvals/script.json').unlink()
    write_json(path, manifest)
    with pytest.raises((ValueError, OSError)):
        gen.render()
    assert not calls


@pytest.mark.parametrize('failure', ['worker', 'probe', 'concurrent'])
def test_failed_render_preserves_previous_video_and_receipt(render_setup, monkeypatch, failure):
    p, gen, _, _, _ = render_setup
    gen.render()
    before = {p.output_dir / name: (p.output_dir / name).read_bytes()
              for name in ['video.mp4', 'video_render.json']}
    original_run = subprocess.run

    def fail(args, **kwargs):
        if args[:2] == ['node', 'scripts/render.mjs']:
            raise subprocess.CalledProcessError(1, args)
        return original_run(args, **kwargs)

    def probe(*args):
        if failure == 'probe':
            raise ValueError('bad export')
        (p.output_dir / 'storyboard.json').write_text('{}')
        return {}

    if failure == 'worker':
        monkeypatch.setattr(renderer.subprocess, 'run', fail)
    else:
        monkeypatch.setattr(renderer, 'probe_video', probe)
    with pytest.raises(ValueError):
        gen.render(force=True)
    assert all(f.read_bytes() == content for f, content in before.items())
    assert not list(p.output_dir.glob('.video-*'))


def test_overwrite_requires_force_and_cli_offline_check(render_setup, tmp_path, monkeypatch):
    from article_video.__main__ import main
    from .test_cli import arguments
    p, gen, calls, planner, _ = render_setup
    (p.output_dir / 'video.mp4').write_bytes(b'previous video')
    with pytest.raises(ValueError, match='--force'):
        gen.render()
    assert not calls
    monkeypatch.setattr('article_video.llm.OpenAIProvider', lambda: planner)
    args = arguments(p, p.article_path, tmp_path)
    assert main([*args, 'render', '--check-inputs']) == 0
    assert not calls
    assert main([*args, 'render', '--force']) == 0
    assert main([*args, 'render', '--concurrency', '0']) == 1


def test_probe_rejects_wrong_codec_missing_audio_frames_and_duration(monkeypatch):
    data = {'streams': [
        {'codec_type': 'video', 'codec_name': 'h264', 'pix_fmt': 'yuv420p',
         'width': 1920, 'height': 1080, 'avg_frame_rate': '30/1', 'nb_frames': '60', 'duration': '2'},
        {'codec_type': 'audio', 'codec_name': 'aac', 'duration': '2'}],
        'format': {'format_name': 'mov,mp4,m4a,3gp,3g2,mj2'}}
    current = data
    monkeypatch.setattr(renderer.subprocess, 'run', lambda *a, **kw:
                        subprocess.CompletedProcess(a, 0, json.dumps(current)))
    manifest = {'duration_frames': 60, 'fps': 30, 'width': 1920, 'height': 1080}
    assert probe_video('video.mp4', manifest) == data
    for field, value in [('codec_name', 'vp9'), ('width', 960), ('nb_frames', '59'),
                         ('duration', '1'), ('avg_frame_rate', '25/1')]:
        current = copy.deepcopy(data)
        current['streams'][0][field] = value
        with pytest.raises(ValueError):
            probe_video('video.mp4', manifest)
    for duration in ['0', 'nan', 'inf']:
        current = copy.deepcopy(data)
        current['streams'][1]['duration'] = duration
        with pytest.raises(ValueError):
            probe_video('video.mp4', manifest)
    current = {'streams': data['streams'][:1]}
    with pytest.raises(ValueError):
        probe_video('video.mp4', manifest)
