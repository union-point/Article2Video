"""Stage CLI. Exit 2 means human review is required, 1 means an error."""
import argparse
from pathlib import Path
import sys

from .pipeline import Pipeline, ReviewRequired
from .schemas import PipelineConfig
from .storage import read_json


def main(argv=None):
    parser = argparse.ArgumentParser(description="Article-to-video Stages 2–5 with evidence and approval")
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
    review = commands.add_parser("review", help="Revalidate a generated or edited artifact")
    review.add_argument("stage", choices=("selection", "facts", "script"))
    review.add_argument("--force", action="store_true", help="Rerun semantic verification")
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
