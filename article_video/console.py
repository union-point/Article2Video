"""CLI presentation only: stage state, live rendering progress and worker output."""
from contextvars import ContextVar
from contextlib import contextmanager
from dataclasses import dataclass
import os
import re
import subprocess
from threading import Thread

from rich.console import Console, Group
from rich.live import Live
from rich.progress import BarColumn, Progress, TaskProgressColumn
from rich.table import Table
from rich.text import Text


STAGES = ('Extraction', 'Selection', 'Facts', 'Script', 'Voiceover', 'Timing',
          'Storyboard', 'Render', 'Fact sheet')
ACTIVE_DISPLAY = ContextVar('pipeline_display', default=None)
STYLES = {'Pending': 'dim', 'Running': 'cyan', 'Completed': 'green',
          'Cached': 'blue', 'Failed': 'red'}


@dataclass
class StageState:
    status: str = 'Pending'
    detail: str = ''


class PipelineDisplay:
    def __init__(self, stages=STAGES, *, verbose=False, console=None):
        self.console = console or Console()
        self.verbose = verbose
        self.interactive = (self.console.is_terminal and self.console.is_interactive
                            and self.console.file.isatty())
        # Explicitly disable control sequences even if FORCE_COLOR is set in a pipe.
        if not self.interactive:
            self.console = Console(file=self.console.file, force_terminal=False, color_system=None,
                                   force_interactive=False, markup=False, highlight=False)
        self.stages = {name: StageState() for name in stages}
        self.progress = Progress(BarColumn(bar_width=24), TaskProgressColumn(), auto_refresh=False)
        self.render_task = self.progress.add_task('Render', total=100, visible=False)
        self.live = None

    def stage_counter(self):
        completed = sum(state.status in {'Completed', 'Cached'} for state in self.stages.values())
        return f'{completed}/{len(self.stages)} stages completed'

    def table(self):
        table = Table.grid(padding=(0, 2))
        table.add_column(min_width=12)
        table.add_column(min_width=10)
        table.add_column()
        for name, state in self.stages.items():
            detail = self.progress if name == 'Render' and state.status == 'Running' else Text(state.detail if state.status == 'Failed' else '')
            table.add_row(Text(name), Text(state.status, style=STYLES[state.status]), detail)
        return Group(Text('Article2Video', style='bold'), table,
                     Text(self.stage_counter(), style='dim'))

    def __enter__(self):
        self.token = ACTIVE_DISPLAY.set(self)
        if self.interactive:
            self.live = Live(self.table(), console=self.console, refresh_per_second=8)
            self.live.start()
        else:
            self.console.print('Article2Video')
        return self

    def __exit__(self, *exc):
        try:
            if self.live:
                self.live.stop()
            else:
                self.console.print(self.stage_counter())
        finally:
            ACTIVE_DISPLAY.reset(self.token)

    def update(self, name, status, detail=''):
        self.stages[name] = StageState(status, detail)
        if self.live:
            self.live.update(self.table(), refresh=True)
        elif status != 'Running':
            suffix = f' — {detail}' if status == 'Failed' and detail else ''
            self.console.print(f'{name}: {status}{suffix}', markup=False, highlight=False)
        if self.verbose and detail and status != 'Failed':
            self.console.print(f'{name}: {detail}', markup=False, highlight=False)

    def render_progress(self, percent):
        # Completion of frames is not completion of export verification.
        self.progress.update(self.render_task, completed=percent, visible=True)

    def summary(self, result):
        self.console.print('Completed:', style='bold')
        for key, label in (('video', 'Video'), ('fact_sheet', 'Fact sheet')):
            self.console.print(f"  {label}: {result[key]}", markup=False, highlight=False, soft_wrap=True)
        for warning in result['warnings']:
            self.console.print(f'WARNING: {warning}', style='yellow', markup=False, highlight=False,
                               soft_wrap=True)
        self.console.print('AI-generated narration.')


@contextmanager
def render_output():
    """Consume existing worker progress without changing subprocess failure/timeout handling.

    Other worker output (including errors) stays visible. A pipe reader lets the
    existing subprocess.run retain ownership of timeout and process cleanup.
    """
    display = ACTIVE_DISPLAY.get()
    if display is None:
        yield {}
        return
    read_fd, write_fd = os.pipe()
    reader = os.fdopen(read_fd, encoding='utf-8', errors='replace')
    writer = os.fdopen(write_fd, 'w')

    def consume():
        with reader:
            for line in reader:
                match = re.fullmatch(r'Rendering (\d+)%\s*', line)
                if match and 0 <= int(match[1]) <= 100:
                    display.render_progress(int(match[1]))
                else:
                    display.console.print(Text.from_ansi(line.rstrip('\n')), highlight=False)

    thread = Thread(target=consume, daemon=True)
    thread.start()
    try:
        yield {'stdout': writer, 'stderr': subprocess.STDOUT}
    finally:
        writer.close()
        thread.join()
