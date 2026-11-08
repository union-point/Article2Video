"""Conservative English quantity and company matching, shared by all three links.

This is a recall filter, not entailment. Units and ratios stay distinct; semantic
verification must still detect a value attached to the wrong company or a lost hedge.
"""
from decimal import Decimal
import re
import unicodedata

SMALL = dict(zip(
    "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen".split(),
    range(20),
))
TENS = dict(zip("twenty thirty forty fifty sixty seventy eighty ninety".split(), range(20, 100, 10)))
ORDINALS = {"first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5, "sixth": 6,
            "seventh": 7, "eighth": 8, "ninth": 9, "tenth": 10}
SCALES = {"thousand": 1000, "million": 1000000, "billion": 1000000000}
NUMBER_WORDS = set(SMALL) | set(TENS) | set(ORDINALS) | set(SCALES) | {"hundred"}
WORD_NUMBER = re.compile(
    r"\b(?:" + "|".join(sorted(NUMBER_WORDS, key=len, reverse=True)) + r")\b", re.I,
)


def _word_value(words):
    total = current = 0
    for word in words:
        if word in SMALL or word in TENS or word in ORDINALS:
            current += (SMALL | TENS | ORDINALS)[word]
        elif word == "hundred":
            current = (current or 1) * 100
        elif word in SCALES:
            total += (current or 1) * SCALES[word]
            current = 0
    return str(total + current)


def normalize_number_words(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).lower().replace("−", "-")
    text = re.sub(r"(\d+(?:,\d{3})*(?:\.\d+)?)\s+(thousand|million|billion)\b",
                  lambda m: str(Decimal(m[1].replace(',', '')) * SCALES[m[2]]), text)
    matches = list(WORD_NUMBER.finditer(text))
    spans = []
    for match in matches:
        word = match.group()
        if spans:
            start, end, words = spans[-1]
            gap = text[end:match.start()]
            # 'between three and five' is a range, not the number eight.
            join_and = gap.strip() == "and" and words[-1] in {"hundred", *SCALES}
            join_tens = gap.strip() in {"", "-"} and words[-1] in TENS and word in SMALL and SMALL[word] < 10
            join_scale = gap.strip() in {"", "-"} and (word in SCALES or word == "hundred")
            join_after_scale = gap.strip() in {"", "-"} and words[-1] in {"hundred", *SCALES}
            if join_and or join_tens or join_scale or join_after_scale:
                spans[-1] = (start, match.end(), words + [word])
                continue
        spans.append((match.start(), match.end(), [word]))
    for start, end, words in reversed(spans):
        text = text[:start] + _word_value(words) + text[end:]
    # Decimal words after integer conversion, e.g. 'four point nine'.
    text = re.sub(r"\b(\d+)\s+point\s+(\d+)\b", r"\1.\2", text)
    return text


def _decimal(value):
    return format(Decimal(value.replace(",", "")).normalize(), "f")


def quantities(text: str) -> set[str]:
    text = normalize_number_words(text).replace("⁄", "/")
    text = re.sub(r"(?<=\d)-(?=\d)", "–", text)
    text = re.sub(r"(\d)(?:st|nd|rd|th)\b", r"\1", text)
    text = re.sub(r"\bper\s+cent\b|\bpercent(?:age)?\b", "%", text)
    text = text.replace("out of", "/")
    number = r"-?\d+(?:,\d{3})*(?:\.\d+)?"
    # Convert suffix currencies as well as symbols. Decimal arithmetic avoids float drift.
    text = re.sub(rf"({number})\s*(?:us\s+)?dollars?\b", r"$\1", text)
    text = re.sub(rf"({number})\s*pounds?\b", r"£\1", text)
    text = re.sub(rf"({number})\s*euros?\b", r"€\1", text)
    for code, symbol in {"usd": "$", "gbp": "£", "eur": "€"}.items():
        text = re.sub(rf"\b{code}\s*({number})", lambda m, symbol=symbol: symbol + m[1], text)
        text = re.sub(rf"({number})\s*{code}\b", lambda m, symbol=symbol: symbol + m[1], text)
    text = re.sub(rf"({number})\s*(thousand|million|billion)\b",
                  lambda m: str(Decimal(m[1].replace(',', '')) * SCALES[m[2]]), text)
    pattern = re.compile(rf"(?<![\w.])(?P<currency>[$£€])?\s*(?P<value>{number})\s*(?P<percent>%)?(?!\w)")
    matches = list(pattern.finditer(text))
    values = []
    for match in matches:
        unit = {"$": "usd", "£": "gbp", "€": "eur"}.get(match["currency"], "percent" if match["percent"] else "number")
        values.append((unit, _decimal(match["value"])))
    result = {f"{unit}:{value}" for unit, value in values}
    for i, (left, right) in enumerate(zip(matches, matches[1:])):
        gap = text[left.end():right.start()].strip()
        left_unit, a = values[i]
        right_unit, b = values[i + 1]
        if gap == "/":
            result.add(f"ratio:{a}/{b}")
        if gap in {"-", "–", "—", "to", "and"}:
            # 'and' counts only in 'between x and y'.
            if gap == "and" and not re.search(r"between\s*$", text[max(0, left.start()-12):left.start()]):
                continue
            unit = left_unit if left_unit != "number" else right_unit
            result.update({f"{unit}:{a}", f"{unit}:{b}", f"range:{unit}:{a}:{b}"})
            if unit != "number":
                result.discard(f"number:{a}")
                result.discard(f"number:{b}")
    # Unrecognized digit-bearing formats must not disappear from the recall
    # filter (e.g. '99k', times, or version strings). Exact spelling can match;
    # otherwise the value is flagged for human review, rather than guessed.
    for raw in re.findall(r"(?<!\w)[+-]?\d[\w,./:%–—-]*", text):
        raw = raw.rstrip(".,:")
        if re.search(r"[a-z_]", raw) or raw.count(".") > 1 or ":" in raw:
            result.add(f"unparsed:{raw}")
    return result


def normalize_name(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).casefold()
    text = re.sub(r"['’]s\b", "", text)
    return re.sub(r"[^\w]+", " ", text).strip()


def contains_name(text: str, name: str) -> bool:
    return f" {normalize_name(name)} " in f" {normalize_name(text)} "


# Grammatical starters and ordinary scene labels are not company candidates.
NAME_STOPWORDS = set("""a an the according in on at from to for by with without and or but
this that these those it its they their we our you your if when how what why which
who where start choose compare measure ask check focus build use keep consider
businesses companies agencies company agency results price pricing costs cost
measurement methodology conclusion introduction overview summary takeaway
best published no not only some most each all more less about as before after
ai seo aeo geo pr crm b2b ppc cro total score rank scorecard technical content
""".split())


class NameMatcher:
    def __init__(self, company_names, aliases):
        self.groups = {name: [name, *variants] for name, variants in aliases.items()}
        for name in company_names:
            self.groups.setdefault(name, [name])

    def candidates(self, text, declared=()):
        names = set(declared)
        for canonical, variants in self.groups.items():
            if any(contains_name(text, variant) for variant in variants):
                names.add(canonical)
        # Catch new/hallucinated names, including a company at sentence start.
        # Conservative heuristics can overflag ordinary proper nouns; human review
        # can accept a flag, while the independent verifier still checks meaning.
        for phrase in re.findall(r"\b[A-Z][A-Za-z0-9’'&-]*(?:\s+[A-Z][A-Za-z0-9’'&-]*)*", text):
            words = [w for w in phrase.split()
                     if normalize_name(w) not in NAME_STOPWORDS
                     and not set(normalize_name(w).split()) <= NUMBER_WORDS]
            if words:
                names.add(" ".join(words))
        return names

    def missing(self, text, sources, declared=()):
        missing = []
        for name in sorted(self.candidates(text, declared)):
            variants = next((v for k, v in self.groups.items()
                             if normalize_name(name) in {normalize_name(x) for x in v}), [name])
            if not any(contains_name(source, variant) for source in sources for variant in variants):
                missing.append(name)
        return missing
