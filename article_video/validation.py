"""Deterministic structural errors and reviewable recall-filter findings."""
import re

from article_parser.sentences import normalize, split_sentences

from .normalization import NameMatcher, contains_name, quantities
from .schemas import Review, ReviewItem
from .storage import digest

RANKING_WORDS = re.compile(r"\b(?:rank(?:ed|ing|s)?|best|top|scor(?:e|ed|es)|better|recommend(?:s|ed|ation)?)\b", re.I)


def add_issue(report, severity, code, target, message):
    item = ReviewItem(id=digest([code, target, message])[:16], code=code, target=target, message=message)
    getattr(report, severity).append(item)


def empty_review(stage, artifact):
    return Review(stage=stage, artifact_sha256=digest(artifact), errors=[], flags=[], checks=[])


def unique(values, description):
    if len(values) != len(set(values)):
        raise ValueError(f"Duplicate {description}")


def validate_selection(selection, index):
    known = set(index.sections)
    ranked = [s.section_id for s in selection.ranked_sections]
    unique(ranked, "ranked sections")
    if set(ranked) != known:
        raise ValueError(f"Selection must rank every catalogue section exactly once; missing={sorted(known-set(ranked))}, unknown={sorted(set(ranked)-known)}")
    if sorted(s.rank for s in selection.ranked_sections) != list(range(1, len(known) + 1)):
        raise ValueError("Section ranks must be contiguous and unique")
    selected = selection.selected_section_ids
    unique(selected, "selected sections")
    if not set(selected) <= known:
        raise ValueError("Selection contains unknown section IDs")
    if not min(5, len(known)) <= len(selected) <= min(7, len(known)):
        raise ValueError("Select 5–7 sections, or all sections when fewer than 5 exist")
    if len(split_sentences(normalize(selection.angle), "angle")) != 1:
        raise ValueError("The selection angle must be one sentence")


def validate_facts(facts, index, selected):
    unique([c.claim_id for c in facts.claims], "claim IDs")
    for claim in facts.claims:
        unique(claim.source_ids, f"citations in {claim.claim_id}")
        for source_id in claim.source_ids:
            if source_id not in index.evidence:
                raise ValueError(f"{claim.claim_id}: unknown evidence ID {source_id}")
            if index.evidence[source_id].section_id not in selected:
                raise ValueError(f"{claim.claim_id}: evidence {source_id} is outside the selected sections")


def script_items(script):
    yield "title", script.title
    for scene in script.scenes:
        yield f"{scene.scene_id}.title", scene.title
        for n, item in enumerate(scene.narration, 1):
            yield f"{scene.scene_id}.narration.{n}", item
        for n, item in enumerate(scene.on_screen, 1):
            yield f"{scene.scene_id}.on_screen.{n}", item


def validate_script(script, approved):
    unique([s.scene_id for s in script.scenes], "scene IDs")
    for scene in script.scenes:
        unique(scene.claim_ids, f"scene claim IDs in {scene.scene_id}")
        used = set().union(*(set(i.claim_ids) for i in [scene.title, *scene.narration, *scene.on_screen]))
        if used != set(scene.claim_ids):
            raise ValueError(f"{scene.scene_id}: claim_ids must exactly match all its text items")
        for item in scene.narration:
            if len(split_sentences(normalize(item.text), "narration")) != 1:
                raise ValueError(f"{scene.scene_id}: each narration item must contain exactly one sentence")
    for target, item in script_items(script):
        unique(item.claim_ids, f"claim references in {target}")
        if not set(item.claim_ids) <= set(approved):
            raise ValueError(f"{target}: unknown or unapproved claim IDs")


def attribution_only(text, publisher, aliases=()):
    """Recognize a publisher used only as a reporting source, not a claim entity.

    This authorizes a name from already approved attribution metadata. It does
    not authorize quantities or conclusions; the full candidate still goes to
    the independent verifier. A self-ranking/report retains its entity check.
    """
    name = re.escape(publisher)
    patterns = [
        rf"\baccording to {name}\b",
        rf"\b{name}['’]s\s+(?:ranking|list|report|assessment|criteria|comparison|methodology)\b",
        rf"\b{name}\s+(?:reports|ranks|rates|scores|recommends|says|lists)\b",
    ]
    remainder = text
    for pattern in patterns:
        remainder = re.sub(pattern, "", remainder, flags=re.I)
    # Do not mistake the publisher as ranked company (including anaphora) for
    # attribution alone. Semantic review still decides the actual relationship.
    return (remainder != text
            and not any(contains_name(remainder, name) for name in [publisher, *aliases])
            and not re.search(r"\b(?:itself|its|it|they|their|them|themselves)\b", remainder, re.I))


def token_checks(report, target, text, source_texts, matcher, company_names=(), link="source", attribution=None):
    source_values = set().union(*(quantities(s) for s in source_texts))
    for value in sorted(quantities(text) - source_values):
        add_issue(report, "flags", "MISSING_VALUE", target, f"{link}: {value} is absent from cited text")
    name_sources = source_texts
    aliases = matcher.groups.get(attribution, [])
    if attribution and attribution_only(text, attribution, aliases):
        name_sources = [*source_texts, attribution]
    for name in matcher.missing(text, name_sources, company_names):
        add_issue(report, "flags", "MISSING_NAME", target, f"{link}: {name} is absent from cited text")


def facts_review(artifact, index, selected, config):
    report = empty_review("facts", artifact)
    try:
        validate_facts(artifact.data, index, selected)
    except ValueError as exc:
        add_issue(report, "errors", "INVALID_FACTS", "facts", str(exc))
        return report
    matcher = NameMatcher(index.company_names, config.company_aliases)
    for claim in artifact.data.claims:
        sources = [index.evidence[s].text for s in claim.source_ids]
        token_checks(report, claim.claim_id, claim.text, sources, matcher, claim.company_names)
        if not (claim.attribution.casefold() == config.publisher.casefold()
                or any(matcher.missing(claim.attribution, [s], [claim.attribution]) == [] for s in sources)):
            add_issue(report, "flags", "ATTRIBUTION_REVIEW", claim.claim_id, f"Attribution {claim.attribution!r} is not established")
    return report


def script_review(artifact, index, approved, config):
    report = empty_review("script", artifact)
    try:
        validate_script(artifact.data, approved)
    except ValueError as exc:
        add_issue(report, "errors", "INVALID_SCRIPT", "script", str(exc))
        return report
    matcher = NameMatcher(index.company_names, config.company_aliases)
    for target, item in script_items(artifact.data):
        claims = [approved[c] for c in item.claim_ids]
        sources = [index.evidence[s].text for c in claims for s in c.source_ids]
        attribution = config.publisher if all(c.attribution.casefold() == config.publisher.casefold() for c in claims) else None
        token_checks(report, target, item.text, [c.text for c in claims], matcher, item.company_names, "approved claims", attribution)
        token_checks(report, target, item.text, sources, matcher, item.company_names, "source sentences", attribution)
        if RANKING_WORDS.search(item.text):
            publisher = re.escape(config.publisher)
            attributed = re.search(
                rf"according to {publisher}\b|\b{publisher}['’]s\b|\b{publisher}\s+(?:reports|ranks|rates|scores|recommends|says|lists)\b",
                item.text, re.I,
            )
            if not attributed:
                add_issue(report, "flags", "RANKING_ATTRIBUTION", target,
                          f"Ranking/opinion language needs explicit attribution to {config.publisher}")
    words = sum(len(re.findall(r"\b[\w]+(?:[’'-][\w]+)*\b", item.text))
                for scene in artifact.data.scenes for item in scene.narration)
    if not config.min_narration_words <= words <= config.max_narration_words:
        add_issue(report, "flags", "NARRATION_LENGTH", "script",
                  f"Narration has {words} words; target is {config.min_narration_words}–{config.max_narration_words}")
    return report
