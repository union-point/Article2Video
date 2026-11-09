"""Presentation state and real worker events without media or paid calls."""
from io import StringIO
import subprocess
import sys

import pytest
from rich.console import Console

from article_video.automation import stage_progress
from article_video.console import ACTIVE_DISPLAY, PipelineDisplay, render_output
from article_video.storage import write_json


def test_pending_running_completed_cached_and_mixed_results(tmp_path):
    stream = StringIO()
    display = PipelineDisplay(('Selection', 'Facts', 'Script'), console=Console(file=stream))
    usage = tmp_path / 'usage.jsonl'
    artifact = tmp_path / 'artifact.json'
    write_json(artifact, {'unchanged': True})
    assert all(s.status == 'Pending' for s in display.stages.values())
    assert display.stage_counter() == '0/3 stages completed'
    with display:
        with stage_progress('Selection', artifact_path=artifact):
            assert display.stages['Selection'].status == 'Running'
            assert display.stages['Facts'].status == 'Pending'
        assert display.stages['Selection'].status == 'Cached'
        assert display.stage_counter() == '1/3 stages completed'
        with stage_progress('Facts', usage):
            usage.write_text('{"event":"cache_hit"}\n{"event":"api_attempt_started"}\n')
        assert display.stages['Facts'].status == 'Completed'
        with stage_progress('Script', usage):
            with usage.open('a') as handle:
                handle.write('{"event":"cache_hit"}\n')
        assert display.stages['Script'].status == 'Cached'
    assert stream.getvalue().splitlines() == [
        'Article2Video', 'Selection: Cached', 'Facts: Completed', 'Script: Cached',
        '3/3 stages completed',
    ]
    assert ACTIVE_DISPLAY.get() is None


def test_failure_propagates_and_leaves_later_stages_pending():
    display = PipelineDisplay(('Facts', 'Script'), console=Console(file=StringIO()))
    failure = ValueError('provider unavailable')
    with pytest.raises(ValueError) as caught, display:
        with stage_progress('Facts'):
            raise failure
    assert caught.value is failure
    assert display.stages['Facts'].status == 'Failed'
    assert display.stages['Script'].status == 'Pending'
    assert display.stage_counter() == '0/2 stages completed'
    assert ACTIVE_DISPLAY.get() is None


@pytest.mark.parametrize('interactive', [False, True])
def test_worker_progress_updates_bar_and_preserves_diagnostics(interactive):
    class TerminalStream(StringIO):
        def isatty(self):
            return interactive

    stream = TerminalStream()
    console = Console(file=stream, force_terminal=interactive, force_interactive=interactive,
                      width=100)
    display = PipelineDisplay(('Render',), console=console)
    with display:
        with stage_progress('Render'):
            with render_output() as options:
                subprocess.run([sys.executable, '-c',
                                'print("Rendering 5%"); print("Rendering 65%"); '
                                'print("\\x1b[33mworker warning\\x1b[0m", flush=True)'], check=True, **options)
            assert display.progress.tasks[0].completed == 65
            assert display.stages['Render'].status == 'Running'
        assert display.stages['Render'].status == 'Completed'
    output = stream.getvalue()
    assert 'worker warning' in output
    assert 'Rendering 5%' not in output and 'Rendering 65%' not in output
    if not interactive:
        assert '\x1b' not in output and '\r' not in output
        assert output.splitlines() == [
            'Article2Video', 'worker warning', 'Render: Completed', '1/1 stages completed',
        ]


def test_worker_failure_keeps_error_and_original_exception():
    stream = StringIO()
    display = PipelineDisplay(('Render',), console=Console(file=stream))
    with pytest.raises(subprocess.CalledProcessError), display:
        with stage_progress('Render'):
            with render_output() as options:
                subprocess.run([sys.executable, '-c',
                                'import sys; print("render failed", file=sys.stderr); sys.exit(3)'],
                               check=True, **options)
    assert display.stages['Render'].status == 'Failed'
    assert 'render failed' in stream.getvalue()


def test_redirected_summary_warnings_literal_paths_and_verbose(tmp_path, monkeypatch):
    monkeypatch.setenv('FORCE_COLOR', '1')
    stream = StringIO()
    display = PipelineDisplay(('Facts',), verbose=True, console=Console(file=stream))
    with display:
        with stage_progress('Facts'):
            pass
    display.summary({'video': 'output/[demo].mp4', 'fact_sheet': 'output/fact_sheet.csv',
                     'warnings': ['Excluded 2 unsupported facts', '3 scenes use approximate timing']})
    text = stream.getvalue()
    assert 'Facts: Completed' in text and 'new results generated' in text
    assert 'output/[demo].mp4' in text and 'output/fact_sheet.csv' in text
    assert 'WARNING: Excluded 2 unsupported facts' in text
    assert 'WARNING: 3 scenes use approximate timing' in text
    assert '\x1b' not in text and '\r' not in text


def test_local_normalization_is_completed_even_when_raw_audio_is_cached(tmp_path):
    usage = tmp_path / 'usage.jsonl'
    display = PipelineDisplay(('Voiceover',), console=Console(file=StringIO()))
    with display:
        with stage_progress('Voiceover', usage):
            usage.write_text('{"event":"cache_hit"}\n{"event":"normalization_finished"}\n')
    assert display.stages['Voiceover'].status == 'Completed'


def test_dumb_terminal_uses_plain_output(monkeypatch):
    monkeypatch.setenv('TERM', 'dumb')

    class TerminalStream(StringIO):
        def isatty(self):
            return True

    stream = TerminalStream()
    display = PipelineDisplay(('Render',), console=Console(file=stream))
    with display:
        with stage_progress('Render'):
            display.render_progress(50)
    assert stream.getvalue() == 'Article2Video\nRender: Completed\n1/1 stages completed\n'
