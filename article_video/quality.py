"""Offline editorial review. Findings are heuristics, never factual verdicts.

This module observes the authored script without rewriting it. It deliberately
does not call a model, repair content, or claim to prove narrative coherence.
"""
from collections import Counter, defaultdict
import re

from .schemas import ScriptQualityReview
from .storage import digest
from .validation import add_issue, script_items

VERSION = "script-quality.v1"
CATEGORIES = ["narration_naturalness", "capitalization", "repetition",
              "scene_coherence", "visual_suitability", "on_screen_text"]
WORDS = re.compile(r"\b[\w]+(?:[’'-][\w]+)*\b")
STOP = set("""a an the and or but of for to in on at by with from as is are was were
be its it that this those these their they has have had can will would should
according says reports lists ranked ranks score best first second third fourth
fifth company companies agency agencies text cited show reveal display use
animate sequence scene title screen layout label labels item items each
""".split())
ACTION = re.compile(r"\b(?:show|reveal|display|arrange|place|highlight|animate|draw|"
                    r"compare|build|slide|fade|split|outline|connect|stack|align)\b", re.I)


def normalized(text):
    return " ".join(WORDS.findall(text.casefold()))


def content_words(text, publisher):
    return set(WORDS.findall(text.casefold())) - STOP - set(WORDS.findall(publisher.casefold()))


def glossary(index, config):
    """Use source spelling and configured aliases, never Python title/capitalize."""
    variants = set(index.company_names) | {config.publisher}
    for name, aliases in config.company_aliases.items():
        variants.update([name, *aliases])
    # Acronyms come from frozen evidence; unrelated vocabulary is not a brand.
    for evidence in index.evidence.values():
        variants.update(re.findall(r"\b[A-Z][A-Z0-9]{1,7}\b", evidence.text))
    forms = defaultdict(set)
    for variant in variants:
        forms[variant.casefold()].add(variant)
    return forms


def script_quality_review(artifact, index, config):
    report = ScriptQualityReview(version=VERSION, artifact_sha256=digest(artifact),
                                 categories=CATEGORIES, flags=[])

    def flag(code, target, message):
        add_issue(report, "flags", "QUALITY_" + code, target, message)

    script = artifact.data
    forms = glossary(index, config)
    for target, item in script_items(script):
        for key, spellings in sorted(forms.items()):
            for match in re.finditer(r"(?<!\w)" + re.escape(key) + r"(?!\w)", item.text, re.I):
                if match.group() not in spellings:
                    flag("CAPITALIZATION", target,
                         f"Use source capitalization {sorted(spellings)!r}, not {match.group()!r}.")
        if ".narration." in target:
            words = WORDS.findall(item.text)
            if words and words[0][0].islower() and words[0] not in forms.get(words[0].casefold(), set()):
                flag("CAPITALIZATION", target, "Narration begins with an unexpected lowercase word.")
            if len(words) > 40 or item.text.count(";") >= 2:
                flag("NATURALNESS", target,
                     "Dense narration: split the idea into shorter spoken sentences without dropping qualifiers.")
        elif target == "title" or target.endswith(".title"):
            if len(WORDS.findall(item.text)) > 8 or re.match(r"according to\b", item.text, re.I) or item.text.endswith("."):
                flag("SCENE_TITLE", target, "Use a concise topic label instead of a full claim or attribution sentence.")

    narration = [(f"{s.scene_id}.narration.{n}", item.text)
                 for s in script.scenes for n, item in enumerate(s.narration, 1)]
    repeated = defaultdict(list)
    openings = defaultdict(list)
    for target, text in narration:
        repeated[normalized(text)].append(target)
        opening = " ".join(WORDS.findall(text.casefold())[:3])
        if len(opening.split()) == 3:
            openings[opening].append(target)
    for targets in repeated.values():
        if len(targets) > 1:
            flag("REPETITION", targets[0], "Identical narration recurs at " + ", ".join(targets) + ".")
    for opening, targets in sorted(openings.items()):
        if len(targets) >= 3 and len(targets) / len(narration) >= .4:
            flag("REPETITION", "script", f"The opening {opening!r} occurs in {len(targets)} narration sentences; vary the phrasing while retaining attribution.")

    directions = Counter(normalized(s.visual_direction) for s in script.scenes)
    mirrored = sum(any(normalized(i.text) == normalized(s.title.text) for i in s.on_screen)
                   for s in script.scenes)
    for scene in script.scenes:
        target = scene.scene_id
        spoken = " ".join(i.text for i in scene.narration)
        spoken_words = content_words(spoken, config.publisher)
        spoken_claims = {c for i in scene.narration for c in i.claim_ids}
        # Citation agreement alone cannot show that a label describes the scene.
        for suffix, item in [("title", scene.title),
                             *[(f"on_screen.{n}", i) for n, i in enumerate(scene.on_screen, 1)]]:
            if (not set(item.claim_ids) & spoken_claims
                    or not content_words(item.text, config.publisher) & spoken_words):
                flag("SCENE_COHERENCE", f"{target}.{suffix}",
                     "This label has no clear claim/topic overlap with the scene's narration; review its relevance.")
        named = [name for name in index.company_names
                 if re.search(r"(?<!\w)" + re.escape(name) + r"(?!\w)", spoken, re.I)]
        title_names = [name for name in named if name.casefold() in scene.title.text.casefold()]
        if title_names and len(title_names) < len(named):
            flag("SCENE_COHERENCE", f"{target}.title",
                 "The title singles out fewer companies than the narration discusses; review whether it describes the whole scene.")
        if not scene.on_screen:
            flag("ON_SCREEN", target, "No on-screen takeaway is supplied.")
        for n, item in enumerate(scene.on_screen, 1):
            if len(WORDS.findall(item.text)) > 8:
                flag("ON_SCREEN", f"{target}.on_screen.{n}", "Shorten this display item to at most eight words while retaining meaning and attribution.")
            if mirrored >= 3 and normalized(item.text) == normalized(scene.title.text):
                flag("ON_SCREEN", f"{target}.on_screen.{n}", "On-screen text repeatedly duplicates scene titles; supply a distinct, cited takeaway.")
        direction = scene.visual_direction
        if directions[normalized(direction)] > 1:
            flag("VISUAL_SUITABILITY", f"{target}.visual_direction",
                 "This production instruction is reused across scenes; specify the scene's subject, layout, and action.")
        if (not ACTION.search(direction)
                or not content_words(direction, config.publisher) & spoken_words):
            flag("VISUAL_SUITABILITY", f"{target}.visual_direction",
                 "No clear scene-specific subject/action is evident; describe a visual tied to the narration.")
        # Production notes bypass factual verification: require human inspection
        # for common ways an illustration could falsely imply measured evidence.
        if re.search(r"\b(?:upward|downward|before[- /]after|growth chart|ranking badge)\b", direction, re.I):
            flag("VISUAL_SUITABILITY", f"{target}.visual_direction",
                 "Check that this chart/badge does not imply uncited measurements or an independent endorsement.")
    return report


def quality_markdown(report):
    lines = ["# Script quality review", "", f"Artifact SHA-256: `{report.artifact_sha256}`", "",
             f"Rules: `{report.version}`. Method: offline deterministic heuristics. Flags: {len(report.flags)}.", "",
             "Checks: " + ", ".join(report.categories) + ".", "",
             "This is editorial review, not factual verification. No text was rewritten and no model was called.",
             "A clean result does not establish natural speech, narrative coherence, or production readiness; human review remains necessary.", ""]
    lines += [f"- `{f.id}` **{f.code}** — {f.target}: {f.message}" for f in report.flags]
    return "\n".join(lines) + "\n"
