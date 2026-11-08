"""Stage CLI. Exit 2 means human review is required, 1 means an error."""
import argparse
from pathlib import Path
import sys

from .pipeline import Pipeline, ReviewRequired
from .schemas import PipelineConfig
from .storage import read_json


def main(argv=None):
    parser = argparse.ArgumentParser(description="Article-to-video Stages 2–7 with evidence and approval")
    parser.add_argument("--article", type=Path, default=Path("output/article.json"))
    parser.add_argument("--output-dir", type=Path, default=Path("output"))
    parser.add_argument("--cache-dir", type=Path, default=Path("cache"))
    parser.add_argument("--config", type=Path, default=Path("pipeline_config.json"))
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("select", "facts", "script", "run"):
        command = commands.add_parser(name)
        command.add_argument("--force", action="store_true", help="Bypass this stage's model caches")
        command.add_argument("--auto-approve", action="store_true",
                             help="Approve clean results automatically; pause on any error or review flag")
    voiceover = commands.add_parser("voiceover", help="Generate normalized WAV from the approved script")
    voiceover.add_argument("--voiceover-config", type=Path, default=Path("voiceover_config.json"))
    voiceover.add_argument("--force", action="store_true", help="Regenerate speech and normalized audio")
    timing = commands.add_parser("timing", help="Align approved narration with Whisper word timestamps")
    timing.add_argument("--timing-config", type=Path, default=Path("timing_config.json"))
    timing.add_argument("--force", action="store_true", help="Bypass the transcription cache; never regenerate script or audio")
    timing.add_argument("--check-inputs", action="store_true", help="Validate approvals and narration offline, without transcription or output writes")
    storyboard = commands.add_parser("storyboard", help="Choose cited Remotion templates from the approved script and timing")
    storyboard.add_argument("--plan-file", type=Path, help="Validate and build an editorial plan offline, without planner requests")
    storyboard.add_argument("--force", action="store_true", help="Bypass the template planner cache")
    storyboard.add_argument("--check-inputs", action="store_true", help="Validate upstream inputs offline without generation or writes")
    review = commands.add_parser("review", help="Revalidate a generated or edited artifact")
    review.add_argument("stage", choices=("selection", "facts", "script"))
    review.add_argument("--force", action="store_true", help="Rerun semantic verification")
    commands.add_parser("review-quality", help="Check script editorial quality offline, without approval or model calls")
    repair = commands.add_parser("repair-facts", help="Repair flagged claims into a separate draft")
    repair.add_argument("--claim-id", action="append", default=[])
    repair.add_argument("--source-id", action="append", default=[], help="Additional selected evidence ID for repair")
    approve = commands.add_parser("approve", help="Record an explicit human review of the exact current content")
    approve.add_argument("stage", choices=("selection", "facts", "script"))
    approve.add_argument("--reviewer", required=True)
    approve.add_argument("--note", default="")
    approve.add_argument("--accept-review-item", action="append", default=[], metavar="ID")
    approve.add_argument("--claim-id", action="append", default=[], help="Approve only these facts (repeatable; default all)")
    args = parser.parse_args(argv)
    try:
        config = PipelineConfig.model_validate(read_json(args.config))
        pipeline = Pipeline(args.article, args.output_dir, args.cache_dir, config)
        if args.command == "storyboard":
            from .storyboard import StoryboardGenerator
            generator = StoryboardGenerator(pipeline)
            if args.check_inputs:
                generator.preflight()
                print("Storyboard inputs valid. No model requests or output writes.")
                return 0
            result = generator.generate(args.force, args.plan_file)
            print(f"Storyboard: {args.output_dir / 'storyboard.json'} ({len(result['scenes'])} scenes)")
            print(f"Review: {args.output_dir / 'storyboard_review.md'}; visual and listening review pending.")
            return 2
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
            print(f"Review: {args.output_dir / 'timing_review.md'}; human listening review remains pending.")
            return 2 if result['issues'] else 0
        if args.command == "review-quality":
            report = pipeline.review_quality()
            print(f"Script quality: {len(report.flags)} flags; see {args.output_dir / 'script_quality_review.md'}")
            return 2 if report.flags else 0
        if args.command == "voiceover":
            from .voiceover import VoiceoverConfig, VoiceoverGenerator
            voice_config = VoiceoverConfig.model_validate(read_json(args.voiceover_config))
            metadata = VoiceoverGenerator(pipeline, voice_config).generate(args.force)
            print(f"Voiceover: {args.output_dir / 'narration.wav'} ({metadata['audio']['duration_seconds']:.1f}s)")
            print("AI-generated narration; human listening review is pending.")
            return 0
        if args.command == "repair-facts":
            from .repairs import repair_facts
            _, report = repair_facts(pipeline, args.claim_id, args.source_id)
            print(f"Targeted repair: {len(report.errors)} errors, {len(report.flags)} flags; original artifacts preserved")
            return 1 if report.errors else 2 if report.flags else 0
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
        artifact = action(args.force, auto_approve=args.auto_approve) if args.command == "run" else action(args.force)
        print(f"Output: {pipeline.path(artifact.stage)}")
        if args.command != "run":
            if args.auto_approve:
                receipt = pipeline.auto_approve(artifact.stage)
                print(f"Approved {artifact.stage} ({receipt.mode}): {args.output_dir / 'approvals' / (artifact.stage + '.json')}")
            else:
                print(f"Review {artifact.stage}_review.md, then approve {artifact.stage} to continue.")
        else:
            print("Stages 2–4 are approved. No audio or later stages were run.")
        return 0
    except ReviewRequired as exc:
        print(f"REVIEW REQUIRED: {exc}")
        return 2
    except (ValueError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
