"""Stage 7: choose safe templates; bind exact approved copy to source and time."""
import json
import math
from pathlib import Path
import subprocess
from typing import Literal

from pydantic import Field

from .alignment import ALIGNMENT_VERSION, align_script, validate_timings
from .audio import audio_hash
from .normalization import contains_name, NameMatcher, normalize_name, quantities
from .prompts import SAFETY
from .schemas import Model, RunInfo
from .storage import digest, read_json, write_json, write_text
from .timing import TimingConfig, TimingGenerator
from .transcription import Transcript, validate_transcript

VERSION = "storyboard.v2"
VIDEO_ROOT = Path(__file__).resolve().parents[1] / "video"
PROMPT = SAFETY + """Choose a reusable visual template for each approved scene, in order.
Return every scene exactly once. First component is title, last is conclusion;
interior scenes use methodology, ranking, statistic or comparison. Never repeat
a component consecutively. Statistic requires a screen item or visual node containing a quantity;
comparison requires at least two screen items. Ranking is a text list, never a
chart or an invented rank. Pick layout (wide or split), animation (calm or brisk),
and theme (paper or slate). No React, colors, new text, or factual additions.
Plan visual explanations, not slides. Choose composition from dossier, pipeline,
network, orbit, ledger, magnitude, dual, checklist. Match title=dossier,
methodology=pipeline/network/orbit, ranking=ledger, statistic=magnitude,
comparison=dual, conclusion=checklist. Use at least three different compositions.
Ranking is ONLY for actual company/ranking content, never generic technical work.
Comparison needs genuinely parallel items; do not imply causation or equivalence.
Choose reveal from draw, focus, cascade. Set primary_node to the most important
node index. Supply 2–6 visual_nodes per scene: each has a short text (max 48 chars)
which MUST be an EXACT contiguous substring of that scene's approved narration
item at narration_index. Prefer concrete subjects, outcomes, responsibilities,
questions or document fields. These nodes organize the explanation; do not repeat
full narration. No invented labels, quantities, chart axes or causal relationships.
Use network for an unordered relationship, pipeline only for an actual process,
orbit for grouped responsibilities, dual for parallel aspects. Vary composition,
theme and visual density deliberately. All visual reveals bind to narration cues.
"""


class VisualNode(Model):
    text: str = Field(min_length=1, max_length=48)
    narration_index: int = Field(ge=0)


class TemplateChoice(Model):
    scene_id: str = Field(min_length=1)
    component: Literal["title", "methodology", "ranking", "statistic", "comparison", "conclusion"]
    layout: Literal["wide", "split"]
    animation: Literal["calm", "brisk"]
    theme: Literal["paper", "slate"]
    composition: Literal['auto', 'dossier', 'pipeline', 'network', 'orbit', 'ledger', 'magnitude', 'dual', 'checklist'] = 'auto'
    reveal: Literal['draw', 'focus', 'cascade'] = 'draw'
    primary_node: int = Field(default=0, ge=0, le=5)
    visual_nodes: list[VisualNode] = Field(default_factory=list, max_length=6)


class StoryboardPlan(Model):
    scenes: list[TemplateChoice] = Field(min_length=6, max_length=8)


def validate_zod(manifest):
    """The same Zod contract gates generation, publication and Studio input."""
    try:
        result = subprocess.run(
            ["node", "scripts/validate.mjs"], cwd=VIDEO_ROOT,
            input=json.dumps(manifest, ensure_ascii=False), text=True,
            capture_output=True, timeout=30, check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ValueError("Storyboard validator unavailable; run npm ci in video/") from exc
    if result.returncode:
        raise ValueError("Storyboard Zod validation failed: " + result.stderr[:2500])


def build_manifest(plan, script, timings, claims, index, aliases=None):
    if [c.scene_id for c in plan.scenes] != [s.scene_id for s in script.scenes]:
        raise ValueError("Storyboard must preserve every approved scene in order")
    if plan.scenes[0].component != "title" or plan.scenes[-1].component != "conclusion":
        raise ValueError("Start with title and end with conclusion")
    previous = None
    scenes = []
    for n, (choice, scene, timing) in enumerate(zip(plan.scenes, script.scenes, timings['scenes'], strict=True)):
        if choice.component == previous:
            raise ValueError("Consecutive templates must differ")
        if 0 < n < len(plan.scenes) - 1 and choice.component in {'title', 'conclusion'}:
            raise ValueError("Title and conclusion are reserved for the boundaries")
        if choice.component == 'comparison' and max(len(scene.on_screen), len(choice.visual_nodes)) < 2:
            raise ValueError("Comparison requires at least two approved screen items")
        if choice.component == 'ranking' and len(scene.on_screen) > 4:
            raise ValueError('Ranking list supports at most four screen items; choose another template')
        if choice.component == 'statistic' and not any(quantities(i.text) for i in [*scene.on_screen, *choice.visual_nodes]):
            raise ValueError("Statistic requires an approved on-screen quantity")
        previous = choice.component
        elements = []
        for i, item in enumerate([scene.title, *scene.on_screen]):
            claim_ids = list(item.claim_ids)
            source_ids = sorted({sid for cid in claim_ids for sid in claims[cid].source_ids})
            # Copy approved text verbatim. Its existing fact/semantic approval is
            # preserved, including explicit human exceptions; no paraphrase here.
            if not source_ids or any(sid not in index.evidence for sid in source_ids):
                raise ValueError('Unknown storyboard evidence')
            sources = [index.evidence[sid].text for sid in source_ids]
            matcher = NameMatcher(index.company_names, aliases or {})
            # Text is already immutable approved copy: check declared/known
            # entities, not capitalized topic words such as "Traditional".
            known = {normalize_name(name) for name in [*matcher.groups, *item.company_names]}
            missing_names = [name for name in matcher.missing(item.text, sources, item.company_names)
                             if normalize_name(name) in known]
            # The script contract allows publisher attribution via claim metadata.
            # Bind that identity to an actual cited sentence from another approved
            # fact, rather than dropping attribution or inventing new wording.
            attributions = {normalize_name(claims[cid].attribution) for cid in item.claim_ids}
            for name in missing_names:
                if normalize_name(name) not in attributions:
                    continue
                supporting = next((c for c in claims.values() if any(
                    contains_name(index.evidence[sid].text, name) for sid in c.source_ids)), None)
                if supporting and supporting.claim_id not in claim_ids:
                    claim_ids.append(supporting.claim_id)
                    source_ids = sorted(set(source_ids) | set(supporting.source_ids))
            sources = [index.evidence[sid].text for sid in source_ids]
            missing_names = [name for name in matcher.missing(item.text, sources, item.company_names)
                             if normalize_name(name) in known]
            missing_values = quantities(item.text) - quantities(' '.join(sources))
            if missing_names or missing_values:
                raise ValueError(f'{scene.scene_id} screen {i} needs source review: names={missing_names}, quantities={sorted(missing_values)}')
            cue = timing if i == 0 else timing['elements'][i - 1]
            start = timing['start_frame'] if i == 0 else max(timing['start_frame'], math.ceil(cue['start'] * timings['fps']))
            end = timing['start_frame'] + timing['duration_frames'] if i == 0 else min(
                timing['start_frame'] + timing['duration_frames'], math.ceil(cue['end'] * timings['fps']))
            if choice.component in {'methodology', 'ranking', 'comparison'}:
                end = timing['start_frame'] + timing['duration_frames']
            elements.append({'element_id': f'{scene.scene_id}.screen_{i}', 'role': 'title' if i == 0 else 'body',
                             'text': item.text, 'claim_ids': claim_ids, 'source_ids': source_ids,
                             'start_frame': start, 'end_frame': end})
        compositions = {'title': ['dossier'], 'methodology': ['pipeline', 'network', 'orbit'],
                        'ranking': ['ledger'], 'statistic': ['magnitude'], 'comparison': ['dual'], 'conclusion': ['checklist']}
        composition = compositions[choice.component][0] if choice.composition == 'auto' else choice.composition
        if composition not in compositions[choice.component]:
            raise ValueError('Composition is incompatible with template')
        nodes = []
        for j, node in enumerate(choice.visual_nodes):
            if node.narration_index >= len(scene.narration) or node.text not in scene.narration[node.narration_index].text:
                raise ValueError('Visual labels must be exact approved narration excerpts')
            item = scene.narration[node.narration_index]
            related = [sentence for sentence in timing['sentences'] if sentence['narration_index'] == node.narration_index and node.text in sentence['text']]
            if not related:
                raise ValueError('Visual node has no matching sentence timing')
            nodes.append({'element_id': f'{scene.scene_id}.node_{j}', 'role': 'body', 'text': node.text,
                          'claim_ids': item.claim_ids,
                          'source_ids': sorted({sid for cid in item.claim_ids for sid in claims[cid].source_ids}),
                          'start_frame': max(timing['start_frame'], math.ceil(related[0]['start'] * timings['fps'])),
                          'end_frame': timing['start_frame'] + timing['duration_frames']})
        if nodes and choice.primary_node >= len(nodes):
            raise ValueError('Primary node index out of range')
        scene_choice = choice.model_dump(exclude={'visual_nodes'})
        scene_choice['composition'] = composition
        scenes.append({**scene_choice, 'visual_nodes': nodes, 'start_frame': timing['start_frame'],
                       'duration_frames': timing['duration_frames'], 'timing_method': timing['method'],
                       'elements': elements})
    return {'schema_version': '1.0', 'stage': 'storyboard', 'template_version': VERSION,
            'width': 1920, 'height': 1080, 'fps': timings['fps'],
            'duration_frames': timings['duration_frames'], 'scenes': scenes}


class StoryboardGenerator:
    def __init__(self, pipeline):
        self.pipeline = pipeline

    def preflight(self):
        try:
            return self._preflight()
        except (KeyError, TypeError, IndexError) as exc:
            raise ValueError('Malformed storyboard input; regenerate the affected upstream artifact') from exc

    def _preflight(self):
        p = self.pipeline
        # Timing preflight validates all approvals using semantic caches only.
        # It never transcribes, generates audio, or refreshes upstream reviews.
        artifact, inputs, _, info, snapshot = TimingGenerator(p, TimingConfig()).preflight()
        timings = read_json(p.output_dir / 'timings.json')
        record = read_json(p.output_dir / 'transcript.json')
        config = TimingConfig.model_validate(timings['config'])
        if config.fps != 30:
            raise ValueError('Stage 7 requires 30 fps timing')
        if timings.get('stage') != 'timing' or timings.get('inputs') != inputs or timings.get('alignment_version') != ALIGNMENT_VERSION:
            raise ValueError('Timings are stale or incompatible with approved narration')
        transcript = Transcript.model_validate(record['data'])
        if (timings.get('transcript_sha256') != digest(record)
                or record.get('data_sha256') != digest(transcript)
                or record.get('audio_sha256') != inputs['audio_sha256']):
            raise ValueError('Transcript provenance mismatch')
        validate_transcript(transcript, info['duration_seconds'], config.duration_tolerance_seconds)
        validate_timings(timings, artifact.data, info['duration_seconds'], config)
        expected = align_script(artifact.data, transcript, info['duration_seconds'], config, p.config.company_aliases)
        if any(timings.get(k) != v for k, v in expected.items()):
            raise ValueError('Timing content differs from reproducible alignment; rerun timing')
        for name in ['timings.json', 'transcript.json']:
            path = p.output_dir / name
            snapshot[path] = audio_hash(path.read_bytes())
        facts = p.load('facts', read_json(p.path('facts'))['inputs'])
        approved_ids = read_json(p.output_dir / 'approvals/facts.json')['approved_claim_ids']
        claims = {c.claim_id: c for c in facts.data.claims if c.claim_id in approved_ids}
        return artifact, timings, claims, snapshot

    def generate(self, force=False, plan_file=None):
        p = self.pipeline
        artifact, timings, claims, snapshot = self.preflight()
        # Copy/length errors cannot be fixed by choosing different templates.
        # Detect them before a paid request; template-specific errors retry below.
        baseline = StoryboardPlan(scenes=[TemplateChoice(
            scene_id=s.scene_id, component='title' if n == 0 else 'conclusion' if n == len(artifact.data.scenes) - 1
            else 'methodology' if n % 2 else 'comparison' if len(s.on_screen) >= 2 else 'ranking',
            layout='wide', animation='calm', theme='paper') for n, s in enumerate(artifact.data.scenes)])
        validate_zod(build_manifest(baseline, artifact.data, timings, claims, p.index, p.config.company_aliases))
        # Check the Node/Zod installation before any paid request.
        probe = subprocess.run(['node', '-e', "import('./src/schema.mjs')"], cwd=VIDEO_ROOT,
                               capture_output=True, text=True, timeout=30)
        if probe.returncode:
            raise ValueError('Storyboard validator unavailable; run npm ci in video/')
        inputs = {**p.base_inputs(), 'script': digest(artifact), 'timings': digest(timings),
                  'schema': audio_hash((VIDEO_ROOT / 'src/schema.mjs').read_bytes())}
        def validate(plan):
            validate_zod(build_manifest(plan, artifact.data, timings, claims, p.index, p.config.company_aliases))
        if plan_file is not None:
            plan = StoryboardPlan.model_validate(read_json(plan_file))
            validate(plan)
            inputs['editorial_plan'] = digest(plan)
            run = RunInfo(requested_model='local-editorial', resolved_model='local-editorial',
                          prompt_version=VERSION, cache_key=digest({'inputs': inputs, 'plan': plan.model_dump()}),
                          response_id=None, usage={})
        else:
            plan, run = p.runner.run('storyboard', model=p.config.generation_model, version=VERSION,
                                    prompt=PROMPT, payload={'inputs': inputs, 'script': artifact.data.model_dump()},
                                    schema=StoryboardPlan, validate=validate, force=force)
        manifest = build_manifest(plan, artifact.data, timings, claims, p.index, p.config.company_aliases)
        manifest.update(inputs=inputs, run=run.model_dump(),
                        review={'status': 'review_required', 'timing_status': timings['status'],
                                'timing_issues': [{k: issue[k] for k in ('code', 'target', 'message')}
                                                  for issue in timings['issues']], 'listening_review': 'pending',
                                'visual_review': 'pending'})
        validate_zod(manifest)
        if any(not path.exists() or audio_hash(path.read_bytes()) != value for path, value in snapshot.items()):
            raise ValueError('An approved input changed during storyboard generation; output not replaced')
        lines = ['# Stage 7 storyboard review', '', 'Status: **review_required**', '',
                 'Screen copy is copied exactly from the approved script. Existing review exceptions remain in effect.',
                 f"Timing status: {timings['status']}; {len(timings['issues'])} findings. Inspect timing_review.md.",
                 'Human listening and visual review remain pending. No video was rendered.', '',
                 '| Scene | Template | Layout / motion / theme | Frames |', '| --- | --- | --- | --- |']
        for scene in manifest['scenes']:
            lines.append(f"| {scene['scene_id']} | {scene['component']} / {scene['composition']} / {scene['reveal']} | {scene['layout']} / {scene['animation']} / {scene['theme']} | {scene['start_frame']} + {scene['duration_frames']} |")
        lines += ['', '## Screen evidence', '']
        for scene in manifest['scenes']:
            for element in [*scene['elements'], *scene['visual_nodes']]:
                lines += [f"- {element['element_id']}: {element['text']}",
                          f"  - Claims: {', '.join(element['claim_ids'])}; sources: {', '.join(element['source_ids'])}"]
        write_json(p.output_dir / 'storyboard.json', manifest)
        write_text(p.output_dir / 'storyboard_review.md', '\n'.join(lines) + '\n')
        return manifest
