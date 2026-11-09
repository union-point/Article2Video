"""Article context, usable evidence and short scripts survive Stages 2–4."""
from article_video import prompts
from article_video.schemas import Facts, Script, Selection
from article_video.storage import read_json
from article_video.validation import validate_selection


def test_main_article_sections_reach_selection_without_truncation(real_index):
    payload = real_index.selection_input()
    for sid in ('block_0001', 'block_0005', 'block_0025', 'block_0046'):
        section = next(s for s in payload['sections'] if s['section_id'] == sid)
        assert len(section['evidence']) == len(real_index.sections[sid].source_ids)
    profiles = next(s for s in payload['sections'] if s['section_id'] == 'block_0025')
    assert len({e['context']['name'] for e in profiles['evidence'] if 'name' in e['context']}) == 9
    comparison = next(s for s in payload['sections'] if s['section_id'] == 'block_0005')
    assert any('table_row' in e['context'] for e in comparison['evidence'])


def test_facts_and_script_receive_article_subject_and_keep_supported_attribution(setup_pipeline):
    p, provider = setup_pipeline

    def qualify(data):
        if isinstance(data, Facts):
            for claim in data.claims:
                claim.attribution = "Acme's recommendation"
            data.claims[0].text = 'Separate branded from non-branded prompts.'
        return data

    provider.transform = qualify
    p.run()
    assert len(p._facts()[2]) == 6
    for stage in ('Facts', 'Script'):
        payload = next(payload for name, payload, _ in provider.calls if name == stage)
        assert payload['article_title'] == p.index.document.article.title
        assert payload['angle'] == read_json(p.path('selection'))['data']['angle']


def test_short_evidence_can_use_two_scenes_through_storyboard(setup_pipeline):
    from article_video.tests.test_timing import transcript_for
    from article_video.alignment import align_script, validate_timings
    from article_video.timing import TimingConfig
    from article_video.storyboard import StoryboardPlan, TemplateChoice, build_manifest, validate_zod
    p, provider = setup_pipeline

    def shorten(data):
        if isinstance(data, Selection):
            data.selected_section_ids = data.selected_section_ids[:1]
        if isinstance(data, Script):
            data.scenes = [data.scenes[0], data.scenes[-1]]
        return data

    provider.transform = shorten
    script = p.run().data
    validate_selection(p._selection()[0].data, p.index)
    config = TimingConfig()
    timing = align_script(script, transcript_for(script), 2, config, p.config.company_aliases)
    validate_timings(timing, script, 2, config)
    plan = StoryboardPlan(scenes=[TemplateChoice(scene_id=s.scene_id, component=component,
        layout='wide', animation='calm', theme='paper') for s, component in zip(script.scenes, ('title', 'conclusion'))])
    manifest = build_manifest(plan, script, timing, p._facts()[2], p.index)
    validate_zod(manifest)
    assert len(manifest['scenes']) == 2


def test_prompt_revision_refreshes_selection_but_reuses_unchanged_generation_cache(setup_pipeline, monkeypatch):
    p, provider = setup_pipeline
    p.run()
    article = p.article_path.read_bytes()
    before = p.path('selection').read_bytes()
    monkeypatch.setitem(prompts.VERSIONS, 'selection', 'selection.test-revision')
    p.run()
    assert p.path('selection').read_bytes() != before
    assert p.article_path.read_bytes() == article
    calls = len(provider.calls)
    p.run()
    assert len(provider.calls) == calls


def test_script_prompt_revision_preserves_selection_and_facts(setup_pipeline, monkeypatch):
    p, provider = setup_pipeline
    p.run()
    paths = [p.article_path, p.path('selection'), p.path('facts'),
             p.output_dir / 'approvals/selection.json', p.output_dir / 'approvals/facts.json']
    before = {path: path.read_bytes() for path in paths}
    monkeypatch.setitem(prompts.VERSIONS, 'script', 'script.test-revision')
    p.run()
    assert all(path.read_bytes() == data for path, data in before.items())
    names = [name for name, _, _ in provider.calls]
    assert names.count('Selection') == names.count('Facts') == 1
    assert names.count('Script') == 2
