"""Stage 7 contract, exact evidence copying, cache, retry and safe publication."""
from pathlib import Path

import pytest

from article_video.llm import ModelRunner
from article_video.storage import read_json, write_json
from article_video.storyboard import StoryboardGenerator, StoryboardPlan, TemplateChoice
from article_video.timing import TimingGenerator
from .test_timing import timing_setup  # noqa: F401 -- shared upstream fixture


class Planner:
    def __init__(self):
        self.calls = 0
        self.invalid = False
        self.callback = None

    def generate(self, **kwargs):
        self.calls += 1
        payload = kwargs['payload'].get('original_input', kwargs['payload'])
        components = ['title', 'methodology', 'ranking', 'methodology', 'ranking', 'conclusion']
        data = StoryboardPlan(scenes=[TemplateChoice(scene_id=s['scene_id'], component=c,
             layout='split', animation='calm', theme='paper') for s, c in zip(payload['script']['scenes'], components)])
        if self.invalid or self.calls == 1:
            data.scenes[0].component = 'ranking'
        if self.callback:
            self.callback()
        return data, dict(resolved_model=kwargs['model'], response_id='fake', usage={'total_tokens': 12})


@pytest.fixture
def storyboard_setup(timing_setup):
    p, config, transcriber, semantic = timing_setup
    TimingGenerator(p, config, transcriber).generate()
    planner = Planner()
    p.runner = ModelRunner(p.runner.cache_dir, planner)
    return p, planner, semantic


def test_retry_cache_copy_and_source_timing_binding(storyboard_setup):
    p, planner, semantic = storyboard_setup
    before = {f: f.read_bytes() for f in p.output_dir.rglob('*') if f.is_file()}
    calls = len(semantic.calls)
    gen = StoryboardGenerator(p)
    manifest = gen.generate()
    assert planner.calls == 2
    assert len(semantic.calls) == calls
    assert all(f.read_bytes() == data for f, data in before.items())
    script = read_json(p.path('script'))['data']
    for scene, original in zip(manifest['scenes'], script['scenes']):
        assert [e['text'] for e in scene['elements']] == [original['title']['text'], *[i['text'] for i in original['on_screen']]]
        assert all(e['source_ids'] and e['claim_ids'] for e in scene['elements'])
    assert gen.generate() == manifest
    assert planner.calls == 2
    assert manifest['duration_frames'] == 66
    assert not (p.output_dir / 'storyboard_review.md').exists()


@pytest.mark.parametrize('file', ['timings.json', 'transcript.json', 'narration.json', 'approvals/script.json'])
def test_stale_input_fails_without_planner(storyboard_setup, file):
    p, planner, _ = storyboard_setup
    path = p.output_dir / file
    data = read_json(path)
    if file == 'timings.json':
        data['scenes'][0]['elements'][0]['start'] = -1
    elif file == 'transcript.json':
        data['data']['text'] += ' altered'
    elif file == 'narration.json':
        data['audio_sha256'] = 'wrong'
    else:
        data['artifact_sha256'] = 'wrong'
    write_json(path, data)
    with pytest.raises(ValueError):
        StoryboardGenerator(p).generate()
    assert planner.calls == 0
    assert not (p.output_dir / 'storyboard.json').exists()


def test_failed_retry_or_concurrent_edit_preserves_outputs(storyboard_setup):
    p, planner, _ = storyboard_setup
    gen = StoryboardGenerator(p)
    gen.generate()
    output = p.output_dir / 'storyboard.json'
    before = output.read_bytes()
    planner.invalid = True
    with pytest.raises(ValueError, match='Start with title'):
        gen.generate(force=True)
    assert output.read_bytes() == before
    planner.invalid = False
    planner.callback = lambda: (p.output_dir / 'timings.json').write_text('{}')
    with pytest.raises(ValueError, match='changed during'):
        gen.generate(force=True)
    assert output.read_bytes() == before


def test_zod_limits_and_template_prerequisites(storyboard_setup):
    from article_video.storyboard import build_manifest, validate_zod
    p, planner, _ = storyboard_setup
    manifest = StoryboardGenerator(p).generate()
    manifest['scenes'][0]['elements'][0]['text'] = 'x' * 81
    with pytest.raises(ValueError, match='80 characters'):
        validate_zod(manifest)
    artifact, timings, claims, _ = StoryboardGenerator(p).preflight()
    plan = StoryboardPlan.model_validate({'scenes': [{k: s[k] for k in ['scene_id', 'component', 'layout', 'animation', 'theme']} for s in manifest['scenes']]})
    plan.scenes[1].component = 'statistic'
    with pytest.raises(ValueError, match='quantity'):
        build_manifest(plan, artifact.data, timings, claims, p.index)
    plan.scenes[1].component = 'comparison'
    with pytest.raises(ValueError, match='at least two'):
        build_manifest(plan, artifact.data, timings, claims, p.index)


def test_cli_check_and_review_exit(storyboard_setup, tmp_path, monkeypatch):
    from article_video.__main__ import main
    from .test_cli import arguments
    p, planner, _ = storyboard_setup
    monkeypatch.setattr('article_video.llm.OpenAIProvider', lambda: planner)
    args = arguments(p, p.article_path, tmp_path)
    assert main([*args, 'storyboard', '--check-inputs']) == 0
    assert planner.calls == 0
    assert main([*args, 'storyboard']) == 0


def test_approved_names_numbers_and_labels_keep_exact_citations(storyboard_setup):
    from article_video.storyboard import build_manifest, validate_zod
    p, _, _ = storyboard_setup
    manifest = StoryboardGenerator(p).generate()
    artifact, timings, claims, _ = StoryboardGenerator(p).preflight()
    plan = StoryboardPlan.model_validate({'scenes': [{k: s[k] for k in ['scene_id', 'component', 'layout', 'animation', 'theme']} for s in manifest['scenes']]})
    scene = artifact.data.scenes[0]
    scene.title.text = 'Three evidence distinctions'
    item = scene.on_screen[0]
    item.text = 'Searchbloom reports 99 percent'
    item.company_names = ['Searchbloom']
    result = build_manifest(plan, artifact.data, timings, claims, p.index, p.config.company_aliases)
    validate_zod(result)
    title, body = result['scenes'][0]['elements']
    assert title['text'] == 'Three evidence distinctions'
    assert body['text'] == item.text
    assert body['claim_ids'] == item.claim_ids
    assert body['source_ids'] == sorted({sid for cid in item.claim_ids for sid in claims[cid].source_ids})
    # Citation integrity still rejects a referenced source that doesn't exist.
    del p.index.evidence[body['source_ids'][0]]
    with pytest.raises(ValueError, match='Unknown storyboard evidence'):
        build_manifest(plan, artifact.data, timings, claims, p.index)


def test_visual_nodes_exact_excerpts_sentence_cues_and_offline_plan(storyboard_setup, tmp_path):
    from article_video.storyboard import VisualNode, build_manifest
    p, planner, _ = storyboard_setup
    artifact, timings, claims, _ = StoryboardGenerator(p).preflight()
    components = ['title', 'methodology', 'ranking', 'methodology', 'ranking', 'conclusion']
    plan = StoryboardPlan(scenes=[TemplateChoice(scene_id=s.scene_id, component=c, layout='wide', animation='calm', theme='slate') for s,c in zip(artifact.data.scenes, components)])
    node = VisualNode(text=artifact.data.scenes[1].narration[0].text[:30], narration_index=0)
    plan.scenes[1].visual_nodes = [node]
    result = build_manifest(plan, artifact.data, timings, claims, p.index)
    visual = result['scenes'][1]['visual_nodes'][0]
    import math
    assert visual['start_frame'] == math.ceil(timings['scenes'][1]['sentences'][0]['start'] * 30)
    assert visual['source_ids'] and visual['claim_ids']
    path = tmp_path / 'editorial.json'
    write_json(path, plan)
    result = StoryboardGenerator(p).generate(plan_file=path)
    assert planner.calls == 0 and result['run']['requested_model'] == 'local-editorial'
    assert 'editorial_plan' in result['inputs']
    plan.scenes[1].visual_nodes[0].text = 'Unsupported invented label'
    with pytest.raises(ValueError, match='exact approved'):
        build_manifest(plan, artifact.data, timings, claims, p.index)
    plan.scenes[1].visual_nodes = []
    plan.scenes[1].composition = 'magnitude'
    with pytest.raises(ValueError, match='incompatible'):
        build_manifest(plan, artifact.data, timings, claims, p.index)


def test_small_timing_inaccuracy_does_not_require_realigning(storyboard_setup):
    p, planner, _ = storyboard_setup
    path = p.output_dir / 'timings.json'
    data = read_json(path)
    data['scenes'][0]['elements'][0]['start'] += .001
    write_json(path, data)
    assert StoryboardGenerator(p).generate()['scenes']


def test_oversized_copy_uses_short_heading_and_omits_whole_optional_label(storyboard_setup):
    from article_video.storyboard import build_manifest, validate_zod
    p, _, _ = storyboard_setup
    manifest = StoryboardGenerator(p).generate()
    artifact, timings, claims, _ = StoryboardGenerator(p).preflight()
    plan = StoryboardPlan.model_validate({'scenes': [{k: s[k] for k in ['scene_id', 'component', 'layout', 'animation', 'theme']} for s in manifest['scenes']]})
    artifact.data.scenes[0].title.text = artifact.data.scenes[0].narration[0].text
    artifact.data.scenes[0].on_screen[0].text = artifact.data.scenes[0].narration[0].text
    result = build_manifest(plan, artifact.data, timings, claims, p.index)
    validate_zod(result)
    assert [e['text'] for e in result['scenes'][0]['elements']] == ['Source evidence']
