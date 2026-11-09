"""Thin URL-to-export orchestration over the existing validated stages."""
import csv
from contextlib import contextmanager
import json
import io
from pathlib import Path
from urllib.parse import urlsplit

from article_parser.exceptions import ExtractionError
from article_parser.fetcher import fetch_html, load_html
from article_parser.registry import extract_article
from article_parser.schemas import ArticleDocument

from .renderer import VideoRenderer
from .storage import read_json, write_json, write_text
from .storyboard import StoryboardGenerator
from .timing import TimingGenerator
from .voiceover import VoiceoverGenerator


@contextmanager
def stage_progress(name, usage_path=None, artifact_path=None):
    """Print progress using existing usage events and small artifact receipts."""
    offset = usage_path.stat().st_size if usage_path and usage_path.exists() else 0
    before = artifact_path.read_bytes() if artifact_path and artifact_path.exists() else None
    print(f"{name}: starting", flush=True)
    try:
        yield
    except Exception as exc:
        print(f"{name}: failed — {exc}", flush=True)
        raise
    else:
        events = []
        if usage_path and usage_path.exists():
            with usage_path.open() as handle:
                handle.seek(offset)
                events = [json.loads(line)['event'] for line in handle if line.strip()]
        reused = 'cache_hit' in events or 'response_reused' in events
        generated = any(e in events for e in ('api_attempt_started', 'provider_attempt_started'))
        if artifact_path:
            reused = reused or (not generated and before is not None and artifact_path.exists()
                                and before == artifact_path.read_bytes())
        detail = 'cache reused; new results generated' if reused and generated else 'cached results reused' if reused else 'new results generated'
        print(f"{name}: finished ({detail})", flush=True)


def prepare_article(url, path, html_file=None, snapshot_dir=Path('snapshots')):
    """Reuse the frozen extraction for the same URL and optional HTML snapshot."""
    parsed = urlsplit(url)
    if parsed.scheme not in {'http', 'https'} or not parsed.hostname:
        raise ValueError('--url must be an absolute HTTP(S) URL')
    try:
        if path.exists():
            document = ArticleDocument.model_validate(read_json(path))
            same_html = html_file is None or load_html(html_file, url).source.html_sha256 == document.source.html_sha256
            if document.source.requested_url == url and same_html:
                return path
        fetched = load_html(html_file, url) if html_file else fetch_html(url, snapshot_dir)
        document = extract_article(fetched.html, fetched.source)
    except ExtractionError as exc:
        raise ValueError(str(exc)) from exc
    payload = document.model_dump(exclude_none=True)
    payload['article'] = document.article.model_dump()
    write_json(path, payload)
    return path


def fact_sheet(pipeline):
    """Pair actual narration statements with their exact cited article sentences."""
    artifact, _ = pipeline.approved_script(cache_only=True)
    _, _, claims = pipeline._facts(cache_only=True)
    stream = io.StringIO(newline='')
    writer = csv.writer(stream)
    writer.writerow(['video_statement', 'article_sentence'])
    seen = set()
    for scene in artifact.data.scenes:
        for statement in scene.narration:
            for claim_id in statement.claim_ids:
                for source_id in claims[claim_id].source_ids:
                    pair = (statement.text, pipeline.index.evidence[source_id].text)
                    if pair not in seen:
                        writer.writerow(pair)
                        seen.add(pair)
    write_text(pipeline.output_dir / 'fact_sheet.csv', stream.getvalue())


def run_all(pipeline, voice_config, timing_config, *, force=False, concurrency=2):
    """The demo's linear path; each existing stage owns its cache and validation."""
    pipeline.run(force, auto_approve=pipeline.mode == 'auto', progress=True)
    usage = pipeline.runner.usage_log.path
    with stage_progress('Voiceover', usage):
        VoiceoverGenerator(pipeline, voice_config).generate()
    with stage_progress('Timing', usage):
        timings = TimingGenerator(pipeline, timing_config).generate()
    with stage_progress('Storyboard', usage):
        StoryboardGenerator(pipeline).generate()
    with stage_progress('Render', artifact_path=pipeline.output_dir / 'video_render.json'):
        receipt = VideoRenderer(pipeline).render(concurrency=concurrency, replace_stale=True)
    with stage_progress('Fact sheet'):
        fact_sheet(pipeline)
    warnings = list(pipeline.warnings)
    count = sum(s['method'] == 'even_fallback' for s in timings['scenes'])
    if count:
        warnings.append(f'{count} scenes use approximate timing')
    return {'video': str(pipeline.output_dir / receipt['video_file']),
            'fact_sheet': str(pipeline.output_dir / 'fact_sheet.csv'),
            'warnings': list(dict.fromkeys(warnings))}
