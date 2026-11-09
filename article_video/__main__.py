"""URL-to-MP4 CLI. Auto is default; review mode opts into human checkpoints."""
import argparse
from contextlib import ExitStack
from pathlib import Path
import sys

from .pipeline import Pipeline, ReviewRequired
from .schemas import PipelineConfig
from .storage import read_json


def main(argv=None):
    parser = argparse.ArgumentParser(description="Article URL to validated MP4 and fact sheet")
    parser.add_argument("--article", type=Path, default=Path("output/article.json"))
    parser.add_argument("--output-dir", type=Path, default=Path("output"))
    parser.add_argument("--cache-dir", type=Path, default=Path("cache"))
    parser.add_argument("--config", type=Path, default=Path("configs/pipeline_config.json"))
    parser.add_argument("--mode", choices=("auto", "review"), default="auto")
    parser.add_argument("--verbose", action="store_true", help="Show stage diagnostics (detailed usage remains in cache/usage.jsonl)")
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("select", "facts", "script", "run"):
        command = commands.add_parser(name)
        command.add_argument("--force", action="store_true", help="Bypass this stage's model caches")
        command.add_argument("--mode", choices=("auto", "review"), default=argparse.SUPPRESS)
        if name == "run":
            command.add_argument("--url", help="Fetch an article URL, reusing its frozen extraction on resume")
            command.add_argument("--html-file", type=Path, help="Optional frozen HTML for offline extraction")
            command.add_argument("--snapshot-dir", type=Path, default=Path("snapshots"))
            command.add_argument("--voiceover-config", type=Path, default=Path("configs/voiceover_config.json"))
            command.add_argument("--timing-config", type=Path, default=Path("configs/timing_config.json"))
            command.add_argument("--concurrency", type=int, default=2)
    voiceover = commands.add_parser("voiceover", help="Generate normalized WAV from the approved script")
    voiceover.add_argument("--voiceover-config", type=Path, default=Path("configs/voiceover_config.json"))
    voiceover.add_argument("--force", action="store_true", help="Regenerate speech and normalized audio")
    timing = commands.add_parser("timing", help="Align approved narration with Whisper word timestamps")
    timing.add_argument("--timing-config", type=Path, default=Path("configs/timing_config.json"))
    timing.add_argument("--force", action="store_true", help="Bypass the transcription cache; never regenerate script or audio")
    timing.add_argument("--check-inputs", action="store_true", help="Validate approvals and narration offline, without transcription or output writes")
    storyboard = commands.add_parser("storyboard", help="Choose cited Remotion templates from the approved script and timing")
    storyboard.add_argument("--plan-file", type=Path, help="Validate and build an editorial plan offline, without planner requests")
    storyboard.add_argument("--force", action="store_true", help="Bypass the template planner cache")
    storyboard.add_argument("--check-inputs", action="store_true", help="Validate upstream inputs offline without generation or writes")
    render = commands.add_parser("render", help="Render cited storyboard and approved narration to H.264/AAC MP4 locally")
    render.add_argument("--check-inputs", action="store_true", help="Revalidate storyboard, upstream approvals and timing offline without rendering")
    render.add_argument("--preview", action="store_true", help="Render a separate 960×540 MP4 with the same audio and clock")
    render.add_argument("--force", action="store_true", help="Replace an existing export only after successful rendering and verification")
    render.add_argument("--concurrency", type=int, default=2, help="Parallel rendering workers (1–16; default 2)")
    review = commands.add_parser("review", help="Revalidate a generated or edited artifact")
    review.add_argument("stage", choices=("selection", "facts", "script"))
    review.add_argument("--force", action="store_true", help="Rerun semantic verification")
    approve = commands.add_parser("approve", help="Record an explicit human review of the exact current content")
    approve.add_argument("stage", choices=("selection", "facts", "script"))
    approve.add_argument("--reviewer", required=True)
    approve.add_argument("--note", default="")
    approve.add_argument("--accept-review-item", action="append", default=[], metavar="ID")
    approve.add_argument("--claim-id", action="append", default=[], help="Approve only these facts (repeatable; default all)")
    # Accept diagnostics before or after the subcommand.
    for command in commands.choices.values():
        command.add_argument('--verbose', action='store_true', default=argparse.SUPPRESS,
                             help='Show stage diagnostics and the usage log path')
    args = parser.parse_args(argv)
    display_stack = ExitStack()
    try:
        if args.command in {'approve', 'review'}:
            args.mode = 'review'
        from .console import PipelineDisplay, STAGES
        display = None
        if args.command == 'run' or (args.command == 'render' and not args.check_inputs):
            display = display_stack.enter_context(PipelineDisplay(
                STAGES if args.command == 'run' else ('Render',), verbose=args.verbose))
        config = PipelineConfig.model_validate(read_json(args.config))
        if args.command == 'run' and args.url:
            from .automation import prepare_article, stage_progress
            with stage_progress('Extraction', artifact_path=args.output_dir / 'article.json'):
                args.article = prepare_article(args.url, args.output_dir / 'article.json', args.html_file,
                                               args.snapshot_dir)
        elif args.command == 'run' and args.html_file:
            raise ValueError('--html-file requires --url')
        from contextlib import nullcontext
        from .automation import stage_progress
        with stage_progress('Extraction', artifact_path=args.article) if args.command == 'run' and not args.url else nullcontext():
            pipeline = Pipeline(args.article, args.output_dir, args.cache_dir, config, mode=args.mode)
        if args.verbose:
            print(f"Diagnostic usage log: {pipeline.runner.usage_log.path}", flush=True)
        if args.command == 'run':
            from .automation import run_all
            from .timing import TimingConfig
            from .voiceover import VoiceoverConfig
            result = run_all(pipeline, VoiceoverConfig.model_validate(read_json(args.voiceover_config)),
                             TimingConfig.model_validate(read_json(args.timing_config)),
                             force=args.force, concurrency=args.concurrency)
            display_stack.close()
            display.summary(result)
            return 0
        if args.command == "render":
            from .renderer import VideoRenderer
            renderer = VideoRenderer(pipeline)
            if args.check_inputs:
                renderer.preflight()
                print("Render inputs valid. No model requests, media rendering or output writes.")
                return 0
            with stage_progress('Render', artifact_path=args.output_dir / ('video_preview_render.json' if args.preview else 'video_render.json')):
                result = renderer.render(preview=args.preview, force=args.force, concurrency=args.concurrency)
            display_stack.close()
            print(f"Video: {args.output_dir / result['video_file']} ({result['duration_frames'] / result['fps']:.1f}s)")
            print("Export verified. Listening and visual review are optional.")
            return 0
        if args.command == "storyboard":
            from .storyboard import StoryboardGenerator
            generator = StoryboardGenerator(pipeline)
            if args.check_inputs:
                generator.preflight()
                print("Storyboard inputs valid. No model requests or output writes.")
                return 0
            result = generator.generate(args.force, args.plan_file)
            print(f"Storyboard: {args.output_dir / 'storyboard.json'} ({len(result['scenes'])} scenes)")
            return 0
        if args.command == "timing":
            from .timing import TimingConfig, TimingGenerator
            timing_config = TimingConfig.model_validate(read_json(args.timing_config))
            generator = TimingGenerator(pipeline, timing_config)
            if args.check_inputs:
                generator.preflight()
                print("Timing inputs valid: selection/facts/script approvals, exact narration text, WAV hash and metadata. No model requests.")
                return 0
            result = generator.generate(args.force)
            print(f"Timing: {args.output_dir / 'timings.json'} ({result['sentence_count']} sentences, {len(result['scenes'])} scenes, {len(result['issues'])} findings)")
            return 2 if result['issues'] and args.mode == 'review' else 0
        if args.command == "voiceover":
            from .voiceover import VoiceoverConfig, VoiceoverGenerator
            voice_config = VoiceoverConfig.model_validate(read_json(args.voiceover_config))
            metadata = VoiceoverGenerator(pipeline, voice_config).generate(args.force)
            print(f"Voiceover: {args.output_dir / 'narration.wav'} ({metadata['audio']['duration_seconds']:.1f}s)")
            print("AI-generated narration; listening review is optional.")
            return 0
        if args.command == "review":
            _, report = pipeline.review(args.stage, args.force)
            print(f"{args.stage}: {len(report.errors)} errors, {len(report.flags)} review flags, {len(report.checks)} semantic checks")
            print(f"Review: {args.output_dir / (args.stage + '_review.md')}")
            return 1 if report.errors else 2 if report.flags else 0
        if args.command == "approve":
            pipeline.approve(args.stage, args.reviewer, args.note, args.accept_review_item, args.claim_id)
            print(f"Approved {args.stage}: {args.output_dir / 'approvals' / (args.stage + '.json')}")
            return 0
        action = pipeline.select if args.command == "select" else getattr(pipeline, args.command)
        artifact = action(args.force)
        print(f"Output: {pipeline.path(artifact.stage)}")
        if args.mode == 'auto':
            receipt = pipeline.auto_approve(artifact.stage)
            print(f"Approved {artifact.stage} ({receipt.mode}): {args.output_dir / 'approvals' / (artifact.stage + '.json')}")
        else:
            print(f"Review {artifact.stage}_review.md, then approve {artifact.stage} to continue.")
        return 0
    except ReviewRequired as exc:
        display_stack.close()
        if args.mode == 'review':
            print(f"REVIEW REQUIRED: {exc}")
            return 2
        print(f"ERROR: {exc}", file=sys.stderr, flush=True)
        return 1
    except (ValueError, OSError) as exc:
        display_stack.close()
        print(f"ERROR: {exc}", file=sys.stderr, flush=True)
        return 1

    finally:
        display_stack.close()


if __name__ == "__main__":
    raise SystemExit(main())
