"""Pinned English pySBD segmentation; offsets refer to normalized source text."""
import re

import pysbd

from .schemas import Sentence

SPLITTER_NAME = "pysbd-en"
SPLITTER_VERSION = "0.3.4+offsets.1"


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def split_sentences(text: str, block_id: str) -> list[Sentence]:
    if not text:
        return []
    if normalize(text) != text:
        raise ValueError("Sentence splitter requires normalized text")
    spans = pysbd.Segmenter(language="en", clean=False, char_span=True).segment(text)
    sentences = []
    for span in spans:
        start, end = span.start, span.end
        while start < end and text[start].isspace():
            start += 1
        while end > start and text[end - 1].isspace():
            end -= 1
        if start < end:
            sentences.append(Sentence(id=f"{block_id}.s{len(sentences) + 1}",
                                      text=text[start:end], start=start, end=end))
    if " ".join(s.text for s in sentences) != text:
        raise ValueError("Sentence splitter did not reconstruct source text")
    return sentences
