"""Human-readable artifacts are derived from the same cited scene data."""
import re


def plain_heading(text):
    return re.sub(r"[\r\n]+", " ", text)


def script_markdown(artifact):
    script = artifact.data
    lines = [f"# {plain_heading(script.title.text)}", "",
             "> Draft until a matching script approval receipt exists.", "",
             "Edit scenes.json, then run review script to regenerate this document.", ""]
    for n, scene in enumerate(script.scenes, 1):
        lines += [f"## {n}. {plain_heading(scene.title.text)}", "",
                  " ".join(item.text for item in scene.narration), "",
                  "Claims: " + ", ".join(scene.claim_ids), ""]
        for i, item in enumerate(scene.narration, 1):
            lines.append(f"- Narration {i}: {', '.join(item.claim_ids)}")
        if scene.on_screen:
            lines += ["", "On-screen text:", ""]
            lines += [f"- {item.text} ({', '.join(item.claim_ids)})" for item in scene.on_screen]
        lines += ["", f"Visual direction: {scene.visual_direction}", ""]
    return "\n".join(lines)


def review_markdown(report, artifact=None, index=None):
    lines = [f"# {report.stage.title()} review", "", f"Artifact SHA-256: `{report.artifact_sha256}`", "",
             f"Errors: {len(report.errors)}. Review flags: {len(report.flags)}. Semantic checks: {len(report.checks)}.", ""]
    for issue in [*report.errors, *report.flags]:
        lines.append(f"- `{issue.id}` **{issue.code}** — {issue.target}: {issue.message}")
    for check in report.checks:
        lines.append(f"- {check.target}: **{check.verdict.status}** — {check.verdict.reason}")
    if artifact is not None and artifact.stage == "selection":
        lines += ["", "## Proposed angle", "", artifact.data.angle, "", "## Full section ranking", ""]
        for section in sorted(artifact.data.ranked_sections, key=lambda s: s.rank):
            selected = "Chosen" if section.section_id in artifact.data.selected_section_ids else "Excluded"
            title = index.sections[section.section_id].title if section.section_id in index.sections else "Unknown section"
            lines += [f"{section.rank}. **{title}** — {selected} (`{section.section_id}`): {section.reason}"]
    if artifact is not None and artifact.stage == "facts":
        for claim in artifact.data.claims:
            lines += ["", f"## {claim.claim_id}", "", claim.text, "", f"Attribution: {claim.attribution}", ""]
            for source_id in claim.source_ids:
                evidence = index.evidence.get(source_id)
                lines += [f"- `{source_id}`: {evidence.text if evidence else 'UNKNOWN EVIDENCE ID'}"]
    return "\n".join(lines) + "\n"
