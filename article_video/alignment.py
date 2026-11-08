"""Deterministic monotonic sentence alignment and sparse, exact word cues."""
from difflib import SequenceMatcher
import math
import re

from article_parser.sentences import normalize, split_sentences

from .normalization import normalize_name, normalize_number_words, quantities

ALIGNMENT_VERSION = 'alignment.v2'


def alignment_text(text, aliases):
    """Share fact-check number/name normalization, then ignore word spacing."""
    text = normalize_number_words(text)
    text = re.sub(r'(?<=\d),(?=\d)', '', text)
    text = re.sub(r'(\d)(?:st|nd|rd|th)\b', r'\1', text)
    text = re.sub(r'\bper\s+cent\b|\bpercent(?:age)?\b', '%', text)
    text = text.replace('out of', '/')
    for pattern, symbol in [(r'\b(?:gbp|pounds?(?: sterling)?)\b', '£'),
                            (r'\b(?:usd|dollars?)\b', '$'), (r'\b(?:eur|euros?)\b', '€')]:
        text = re.sub(pattern, symbol, text)
    # Keep spoken unit words in the alignment so they cannot slip into the next
    # sentence merely because punctuation/spacing is ignored.
    for symbol, unit in [('%', 'percent'), ('£', 'gbp'), ('$', 'usd'), ('€', 'eur')]:
        text = text.replace(symbol, f' {unit} ')
    text = normalize_name(text)
    groups = [(variant, canonical) for canonical, variants in aliases.items()
              for variant in [canonical, *variants]]
    for variant, canonical in sorted(groups, key=lambda pair: -len(pair[0])):
        text = re.sub(r'(?<!\w)' + re.escape(normalize_name(variant)) + r'(?!\w)',
                      normalize_name(canonical).replace(' ', ''), text)
    return re.sub(r'\W+', '', text)


def script_sentences(script):
    result = []
    for scene in script.scenes:
        for i, item in enumerate(scene.narration):
            for sentence in split_sentences(normalize(item.text), f'{scene.scene_id}.n{i + 1}'):
                result.append({'sentence_id': sentence.id, 'scene_id': scene.scene_id,
                               'narration_index': i, 'text': sentence.text,
                               'char_start': sentence.start, 'char_end': sentence.end,
                               'claim_ids': item.claim_ids})
    return result


def partition_sentences(sentences, words, aliases, beam_width=12):
    """Beam-search partitions: every transcript word is consumed exactly once.

    A bounded search keeps long inputs practical. Low scores are surfaced, never
    repaired by changing text or jumping backwards over unmatched words.
    """
    if len(words) < len(sentences):
        raise ValueError('Too few timestamped words for sentence alignment')
    # Normalizing whole spans also handles numbers spoken across several words.
    span_cache = {}
    def span(start, end):
        key = start, end
        if key not in span_cache:
            span_cache[key] = alignment_text(' '.join(w.word for w in words[start:end]), aliases)
        return span_cache[key]
    beam = {0: (0., [])}
    for i, sentence in enumerate(sentences):
        target = alignment_text(sentence['text'], aliases)
        if not target:
            raise ValueError('Script sentence has no alignable text')
        next_beam = {}
        remaining = len(sentences) - i - 1
        for start, (cost, path) in beam.items():
            # Allow substantial ASR tokenization differences without unbounded search.
            limit = min(len(words) - remaining, start + max(20, len(sentence['text'].split()) * 2 + 12))
            ends = [len(words)] if remaining == 0 else range(start + 1, limit + 1)
            for end in ends:
                candidate = span(start, end)
                score = SequenceMatcher(None, target, candidate, autojunk=False).ratio()
                new_cost = cost + (1 - score) * len(target)
                if end not in next_beam or new_cost < next_beam[end][0]:
                    next_beam[end] = (new_cost, [*path, (start, end, score)])
        beam = dict(sorted(next_beam.items(), key=lambda pair: pair[1][0])[:beam_width])
    if len(words) not in beam:
        raise ValueError('Cannot partition transcript monotonically')
    return beam[len(words)][1]


def sparse_cues(scene, sentences, words, aliases, max_cues):
    cues, seen = [], set()
    for sentence in sentences:
        item = scene.narration[sentence['narration_index']]
        names = [name for name in dict.fromkeys([*item.company_names, *aliases])
                 if alignment_text(name, aliases) in alignment_text(sentence['text'], aliases)]
        numbers = sorted(quantities(sentence['text']))
        # Alternate a name and quantity so a long company list cannot fill every slot.
        targets = [('name', n) for n in names[:1]] + [('quantity', n) for n in numbers]
        for kind, value in targets:
            if (kind, value) in seen:
                continue
            for start in range(sentence['word_start'], sentence['word_end']):
                found = False
                for end in range(start + 1, min(sentence['word_end'], start + 12) + 1):
                    phrase = ' '.join(w.word for w in words[start:end])
                    matches = (alignment_text(phrase, aliases) == alignment_text(value, aliases)
                               if kind == 'name' else value in quantities(phrase))
                    if matches:
                        # A multiword cue can have positive outer bounds even
                        # when an internal word has no usable timestamp.
                        if any(w.end <= w.start for w in words[start:end]):
                            continue
                        if not sentence['start'] <= words[start].start < words[end - 1].end <= sentence['end']:
                            continue
                        cues.append({'kind': kind, 'value': value, 'sentence_id': sentence['sentence_id'],
                                     'start': words[start].start, 'end': words[end - 1].end,
                                     'transcript_text': phrase, 'word_start': start, 'word_end': end})
                        seen.add((kind, value))
                        found = True
                        break
                if found:
                    break
            if len(cues) >= max_cues:
                return sorted(cues, key=lambda cue: cue['start'])
    return sorted(cues, key=lambda cue: cue['start'])


def align_script(script, transcript, duration, config, aliases):
    sentences = script_sentences(script)
    partitions = partition_sentences(sentences, transcript.words, aliases)
    issues = []
    if transcript.omitted_empty_word_count:
        issues.append({'code': 'EMPTY_TRANSCRIPT_WORDS', 'target': 'transcript',
                       'message': f'{transcript.omitted_empty_word_count} empty word entries omitted; full API response retained in the diagnostic receipt'})
    for sentence, (start, end, score) in zip(sentences, partitions, strict=True):
        phrase = ' '.join(w.word for w in transcript.words[start:end])
        missing = quantities(sentence['text']) - quantities(phrase)
        extra = quantities(phrase) - quantities(sentence['text'])
        sentence.update(word_start=start, word_end=end, score=score, transcript_text=phrase,
                        start=transcript.words[start].start, end=transcript.words[end - 1].end,
                        aligned_start=transcript.words[start].start,
                        aligned_end=transcript.words[end - 1].end,
                        method='aligned')
        zero_indices = [n for n in range(start, end)
                        if transcript.words[n].end == transcript.words[n].start]
        sentence['zero_duration_word_indices'] = zero_indices
        sentence['boundary_timestamp_review'] = start in zero_indices or end - 1 in zero_indices
        if zero_indices:
            issues.append({'code': 'ZERO_DURATION_WORD', 'target': sentence['sentence_id'],
                           'word_indices': zero_indices, 'word_count': len(zero_indices),
                           'boundary_affected': sentence['boundary_timestamp_review'],
                           'message': f'{len(zero_indices)} words have zero duration; retain usable sentence bounds, suppress cues using these words, and review timestamps'})
        if any(n and transcript.words[n].start < transcript.words[n - 1].end
               for n in range(start, min(end + 1, len(transcript.words)))):
            issues.append({'code': 'OVERLAPPING_WORDS', 'target': sentence['sentence_id'],
                           'message': 'Whisper word intervals overlap; use scene fallback'})
        if score < config.min_sentence_score:
            issues.append({'code': 'LOW_SENTENCE_SCORE', 'target': sentence['sentence_id'],
                           'message': f'Match score {score:.3f} is below {config.min_sentence_score:.3f}'})
        if missing or extra:
            issues.append({'code': 'QUANTITY_MISMATCH', 'target': sentence['sentence_id'],
                           'message': f'Missing quantities: {sorted(missing)}; extra: {sorted(extra)}'})
        scene = next(s for s in script.scenes if s.scene_id == sentence['scene_id'])
        names = scene.narration[sentence['narration_index']].company_names
        absent_names = [name for name in names
                        if alignment_text(name, aliases) in alignment_text(sentence['text'], aliases)
                        and alignment_text(name, aliases) not in alignment_text(phrase, aliases)]
        if absent_names:
            issues.append({'code': 'NAME_MISMATCH', 'target': sentence['sentence_id'],
                           'message': f'Company names not recognized exactly after normalization: {absent_names}'})
    whole_script = alignment_text(' '.join(s['text'] for s in sentences), aliases)
    whole_words = alignment_text(' '.join(w.word for w in transcript.words), aliases)
    overall = SequenceMatcher(None, whole_script, whole_words, autojunk=False).ratio()
    text_score = SequenceMatcher(None, alignment_text(transcript.text, aliases), whole_words, autojunk=False).ratio()
    if min(overall, text_score) < config.min_sentence_score:
        issues.append({'code': 'TRANSCRIPT_MISMATCH', 'target': 'timing',
                       'message': f'Whole-script score {overall:.3f}; transcript text/words score {text_score:.3f}'})
    groups = [[s for s in sentences if s['scene_id'] == scene.scene_id] for scene in script.scenes]
    # Each scene owns the pause before its next scene; the first starts at zero.
    boundaries = [0.] + [group[0]['start'] for group in groups[1:]] + [duration]
    if any(not a < b for a, b in zip(boundaries, boundaries[1:])):
        raise ValueError('Transcript cannot provide positive, ordered scene boundaries')
    frames = [math.ceil(t * config.fps) for t in boundaries]
    frames[-1] += config.tail_padding_frames
    scenes = []
    for i, (scene, group) in enumerate(zip(script.scenes, groups, strict=True)):
        start, end = boundaries[i:i + 2]
        # Word-level zero spans are review findings, not evidence that the
        # sentence's outer interval is unusable. Other findings still block.
        prior_end = start
        for sentence in group:
            if not prior_end <= sentence['start'] < sentence['end'] <= end:
                issues.append({'code': 'INVALID_SENTENCE_BOUNDS', 'target': sentence['sentence_id'],
                               'message': 'Aligned sentence bounds are not positive and ordered inside the scene; use scene fallback'})
            prior_end = sentence['end']
        bad_ids = {issue['target'] for issue in issues if issue['code'] != 'ZERO_DURATION_WORD'}
        fallback = any(s['sentence_id'] in bad_ids for s in group) or 'timing' in bad_ids
        if fallback:
            issues.append({'code': 'SCENE_FALLBACK', 'target': scene.scene_id,
                           'message': 'Sentence and element cues spread evenly over the estimated scene span; scene boundaries need review'})
            for n, sentence in enumerate(group):
                sentence.update(start=start + (end - start) * n / len(group),
                                end=end if n + 1 == len(group) else start + (end - start) * (n + 1) / len(group),
                                method='even_fallback')
        elements = []
        for n, item in enumerate(scene.on_screen):
            related = [s for s in group if set(s['claim_ids']) & set(item.claim_ids)]
            cue_start = start + (end - start) * n / max(1, len(scene.on_screen))
            cue_end = end if n + 1 == len(scene.on_screen) else start + (end - start) * (n + 1) / len(scene.on_screen)
            if not fallback and related:
                cue_start, cue_end = related[0]['start'], related[-1]['end']
            elements.append({'element_index': n, 'claim_ids': item.claim_ids, 'start': cue_start,
                             'end': cue_end, 'method': 'even_fallback' if fallback or not related else 'claim_sentence'})
        scenes.append({'scene_id': scene.scene_id, 'start': start, 'end': end,
                       'start_frame': frames[i], 'duration_frames': frames[i + 1] - frames[i],
                       'method': 'even_fallback' if fallback else 'aligned', 'sentences': group,
                       'elements': elements, 'word_cues': [] if fallback else sparse_cues(
                           scene, group, transcript.words, aliases, config.max_word_cues_per_scene)})
    return {'audio_duration_seconds': duration, 'fps': config.fps,
            'duration_frames': frames[-1], 'tail_padding_frames': config.tail_padding_frames,
            'sentence_count': len(sentences), 'overall_score': overall,
            'zero_duration_word_count': sum(w.start == w.end for w in transcript.words),
            'transcript_text_score': text_score, 'status': 'review_required' if issues else 'valid',
            'issues': issues, 'scenes': scenes}


def validate_timings(result, script, duration, config):
    expected = script_sentences(script)
    actual = [s for scene in result['scenes'] for s in scene['sentences']]
    if result['sentence_count'] != len(expected) or [s['sentence_id'] for s in actual] != [s['sentence_id'] for s in expected]:
        raise ValueError('Timing sentence count or order differs from approved script')
    if [s['scene_id'] for s in result['scenes']] != [s.scene_id for s in script.scenes]:
        raise ValueError('Timing scene order differs from script')
    previous = 0.
    frame = 0
    for scene in result['scenes']:
        if scene['start'] != previous or not scene['start'] < scene['end'] <= duration:
            raise ValueError('Invalid scene time bounds')
        if scene['start_frame'] != frame or scene['duration_frames'] <= 0:
            raise ValueError('Invalid scene frame bounds')
        prior_end = scene['start']
        for sentence in scene['sentences']:
            if not prior_end <= sentence['start'] < sentence['end'] <= scene['end']:
                raise ValueError('Sentence times are not monotonic within scene')
            if sentence['method'] == 'aligned' and sentence['score'] < config.min_sentence_score:
                raise ValueError('Low-score alignment was not marked as fallback')
            prior_end = sentence['end']
        for cue in [*scene['elements'], *scene['word_cues']]:
            if not scene['start'] <= cue['start'] < cue['end'] <= scene['end']:
                raise ValueError('Cue is outside its scene')
        previous = scene['end']
        frame += scene['duration_frames']
    if previous != duration or frame != math.ceil(duration * config.fps) + config.tail_padding_frames:
        raise ValueError('Timings do not cover the audio master clock')
