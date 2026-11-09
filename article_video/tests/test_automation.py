"""The unattended demo's fact grounding, media output and cache behavior."""
import csv
from pathlib import Path
import subprocess

import pytest

from article_video import automation, renderer
from article_video.__main__ import main
from article_video.schemas import Verdict
from article_video.storage import read_json
from article_video.storyboard import StoryboardPlan
from article_video.timing import TimingConfig, TimingGenerator
from article_video.voiceover import VoiceoverConfig, VoiceoverGenerator
from .test_cli import arguments
from .test_storyboard import Planner
from .test_timing import FakeTranscription, transcript_for
from .test_voiceover import FakeNormalizer, FakeSpeech


@pytest.fixture
def automation_setup(setup_pipeline, monkeypatch):
    p, provider = setup_pipeline
    planner = Planner()
    generate = provider.generate
    provider.generate = lambda **kw: planner.generate(**kw) if kw['schema'] is StoryboardPlan else generate(**kw)
    speech, normalizer = FakeSpeech(), FakeNormalizer()
    transcriber = FakeTranscription(None)
    transcriber.callback = lambda: setattr(transcriber, 'transcript', transcript_for(p.approved_script()[0].data))
    monkeypatch.setattr(automation, 'VoiceoverGenerator', lambda pipeline, config:
                        VoiceoverGenerator(pipeline, config, speech, normalizer))
    monkeypatch.setattr(automation, 'TimingGenerator', lambda pipeline, config:
                        TimingGenerator(pipeline, config, transcriber))
    original_run = subprocess.run
    renders = []

    def worker(args, **kwargs):
        if args[:2] != ['node', 'scripts/render.mjs']:
            return original_run(args, **kwargs)
        job = read_json(Path(args[2]))
        renders.append(job)
        Path(job['output']).write_bytes(b'mocked mp4')
        return subprocess.CompletedProcess(args, 0)

    monkeypatch.setattr(renderer.subprocess, 'run', worker)
    monkeypatch.setattr(renderer, 'probe_video', lambda *args: {'checked': True})
    config = VoiceoverConfig.model_validate(read_json(Path(__file__).resolve().parents[2] / 'configs' / 'voiceover_config.json'))
    return p, provider, speech, transcriber, renders, planner, config


def test_default_cli_completes_and_resumes_without_paid_or_render_calls(automation_setup, tmp_path, monkeypatch, capsys):
    p, provider, speech, transcriber, renders, planner, _ = automation_setup
    monkeypatch.setattr('article_video.llm.OpenAIProvider', lambda: provider)
    args = arguments(p, p.article_path, tmp_path)
    assert main([*args, 'run']) == 0
    first_output = capsys.readouterr().out
    assert 'Completed:' in first_output
    for stage in ('Extraction', 'Selection', 'Facts', 'Script', 'Voiceover', 'Timing', 'Storyboard', 'Render', 'Fact sheet'):
        assert f'{stage}: starting' in first_output
        assert f'{stage}: finished' in first_output
    assert len(renders) == transcriber.calls == len(speech.calls) == 1
    assert not list(p.output_dir.glob('*review*'))
    assert not (p.output_dir / 'history').exists()
    files = {path: path.read_bytes() for path in p.output_dir.rglob('*') if path.is_file()}
    counts = len(provider.calls), len(speech.calls), transcriber.calls, len(renders), planner.calls
    assert main([*args, 'run']) == 0
    assert counts == (len(provider.calls), len(speech.calls), transcriber.calls, len(renders), planner.calls)
    resumed_output = capsys.readouterr().out
    for stage in ('Selection', 'Facts', 'Script', 'Voiceover', 'Timing', 'Storyboard', 'Render'):
        assert f'{stage}: finished (cached results reused)' in resumed_output
    assert all(path.read_bytes() == data for path, data in files.items())
    with (p.output_dir / 'fact_sheet.csv').open(newline='') as stream:
        reader = csv.DictReader(stream)
        assert reader.fieldnames == ['video_statement', 'article_sentence']
        rows = list(reader)
    script = p.approved_script(cache_only=True)[0].data
    assert {row['video_statement'] for row in rows} == {
        statement.text for scene in script.scenes for statement in scene.narration
    }
    assert all(row['article_sentence'] in {e.text for e in p.index.evidence.values()} for row in rows)


def test_fact_sheet_preserves_exact_pairs_and_deduplicates_across_claims_and_scenes(setup_pipeline, monkeypatch):
    p, provider = setup_pipeline
    p.run()
    artifact, receipt = p.approved_script(cache_only=True)
    facts, facts_receipt, claims = p._facts(cache_only=True)
    first, second, third = list(claims.values())[:3]
    source_text = 'Acme says, "Keep the evidence."\nReview the original observations.'
    p.index.evidence[second.source_ids[0]].text = source_text
    # Multiple claims can share sources, and distinct IDs can contain identical text.
    first.source_ids += [*second.source_ids, *third.source_ids]
    statement = artifact.data.scenes[0].narration[0]
    statement.text = 'Acme says, "Keep the evidence," for review.'
    statement.claim_ids = [first.claim_id, second.claim_id]
    artifact.data.scenes[1].narration.append(statement.model_copy(deep=True))
    monkeypatch.setattr(p, 'approved_script', lambda *, cache_only: (artifact, receipt))
    monkeypatch.setattr(p, '_facts', lambda *, cache_only: (facts, facts_receipt, claims))
    calls = len(provider.calls)

    automation.fact_sheet(p)

    path = p.output_dir / 'fact_sheet.csv'
    with path.open(newline='') as stream:
        reader = csv.reader(stream)
        assert next(reader) == ['video_statement', 'article_sentence']
        pairs = list(reader)
    original_source = p.index.evidence[first.source_ids[0]].text
    assert pairs == [
        [statement.text, original_source],
        [statement.text, source_text],
        [artifact.data.scenes[1].narration[0].text, source_text],
        *[[scene.narration[0].text, original_source] for scene in artifact.data.scenes[2:]],
    ]
    original_csv = path.read_bytes()
    automation.fact_sheet(p)
    assert path.read_bytes() == original_csv
    assert len(provider.calls) == calls


def test_timing_only_change_keeps_models_and_audio(automation_setup):
    p, provider, speech, transcriber, renders, _, config = automation_setup
    automation.run_all(p, config, TimingConfig())
    before = {p.path(s): p.path(s).read_bytes() for s in ('selection', 'facts', 'script')}
    before[p.output_dir / 'narration.wav'] = (p.output_dir / 'narration.wav').read_bytes()
    count = len(provider.calls)
    automation.run_all(p, config, TimingConfig(tail_padding_frames=12))
    assert len(provider.calls) == count and len(speech.calls) == transcriber.calls == 1
    assert len(renders) == 2
    assert all(path.read_bytes() == data for path, data in before.items())


def test_failed_export_preserves_video_and_resumes(automation_setup, monkeypatch):
    p, _, speech, transcriber, _, _, config = automation_setup
    automation.run_all(p, config, TimingConfig())
    old_video = (p.output_dir / 'video.mp4').read_bytes()
    original = renderer.probe_video
    monkeypatch.setattr(renderer, 'probe_video', lambda *args: (_ for _ in ()).throw(ValueError('invalid MP4')))
    with pytest.raises(ValueError, match='invalid MP4'):
        automation.run_all(p, config, TimingConfig(tail_padding_frames=12))
    assert (p.output_dir / 'video.mp4').read_bytes() == old_video
    monkeypatch.setattr(renderer, 'probe_video', original)
    automation.run_all(p, config, TimingConfig(tail_padding_frames=12))
    assert len(speech.calls) == transcriber.calls == 1


def test_review_mode_stops_before_media(automation_setup, tmp_path, monkeypatch):
    p, provider, speech, transcriber, renders, _, _ = automation_setup
    monkeypatch.setattr('article_video.llm.OpenAIProvider', lambda: provider)
    assert main([*arguments(p, p.article_path, tmp_path), 'run', '--mode', 'review']) == 2
    assert not speech.calls and not renders and transcriber.calls == 0


def test_url_extraction_reuses_frozen_html_and_rejects_invalid_urls(tmp_path, monkeypatch):
    fixture = Path(__file__).resolve().parents[2] / 'article_parser/tests/fixtures/searchbloom_article.html'
    url = 'https://www.searchbloom.com/strategy/best-ai-seo-agency-companies-services-usa'
    path = tmp_path / 'article.json'
    automation.prepare_article(url, path, fixture)
    original = path.read_bytes()
    monkeypatch.setattr(automation, 'fetch_html', lambda *args: pytest.fail('unnecessary refetch'))
    assert automation.prepare_article(url, path) == path
    assert path.read_bytes() == original
    assert main(['--output-dir', str(tmp_path), 'run', '--url', 'invalid-url']) == 1
    assert path.read_bytes() == original


@pytest.mark.parametrize('verdict', ['partial', 'unsupported'])
def test_only_supported_facts_advance_without_repair_or_extra_artifacts(setup_pipeline, verdict):
    p, provider = setup_pipeline
    generate = provider.generate

    def mixed(**kwargs):
        data, info = generate(**kwargs)
        if kwargs['schema'] is Verdict and kwargs['payload'].get('candidate', {}).get('claim_id') == 'claim_002':
            data.status = verdict
        return data, info

    provider.generate = mixed
    p.run()
    facts, receipt, usable = p._facts()
    assert len(facts.data.claims) == 6  # Keep the original, use a supported subset.
    assert len(usable) == 5 and 'claim_002' not in receipt.approved_claim_ids
    sent = next(payload for name, payload, _ in provider.calls if name == 'Script')
    assert len(sent['approved_claims']) == 5
    assert not list(p.output_dir.glob('*repair*'))
    calls = len(provider.calls)
    p.run()
    assert len(provider.calls) == calls


def test_script_has_one_grounding_pass_and_no_repair_loop(setup_pipeline):
    p, provider = setup_pipeline
    generate = provider.generate

    def reject_script(**kwargs):
        data, info = generate(**kwargs)
        if kwargs['schema'] is Verdict and 'approved_claims' in kwargs['payload']:
            data.status = 'unsupported'
        return data, info

    provider.generate = reject_script
    with pytest.raises(ValueError, match='unsupported content'):
        p.run()
    assert not (p.output_dir / 'approvals/script.json').exists()
    assert [name for name, _, _ in provider.calls].count('Script') == 1
    assert not list(p.output_dir.glob('*candidate*'))


def test_stage_progress_flushes_and_identifies_failure(monkeypatch):
    messages = []
    monkeypatch.setattr('builtins.print', lambda *args, **kwargs: messages.append((args, kwargs)))
    with pytest.raises(ValueError, match='provider unavailable'):
        with automation.stage_progress('Voiceover'):
            assert messages[-1] == (('Voiceover: starting',), {'flush': True})
            raise ValueError('provider unavailable')
    assert messages[-1] == (('Voiceover: failed — provider unavailable',), {'flush': True})
