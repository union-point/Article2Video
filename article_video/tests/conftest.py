"""Deterministic synthetic article and injectable model, with no paid API calls."""
from pathlib import Path

import pytest

from article_parser.schemas import (Article, ArticleDocument, Block, Extraction, Source, Validation)
from article_parser.sentences import split_sentences
from article_video.pipeline import Pipeline
from article_video.schemas import (CitedText, Claim, Facts, PipelineConfig, RankedSection,
                                   Scene, Script, Selection, Verdict)
from article_video.storage import write_json


LONG_SENTENCE = (
    "Acme reports that its measurement process starts with a documented baseline and compares "
    "the same questions over time while keeping the original evidence available for review "
    "so that teams can inspect the underlying observations and understand the limits of each "
    "comparison before deciding whether the reported changes are useful for their own work."
)


class FakeProvider:
    def __init__(self):
        self.calls = []
        self.verdict = "supported"
        self.transform = None

    def generate(self, *, model, prompt, payload, schema, max_output_tokens):
        self.calls.append((schema.__name__, payload, model))
        payload = payload.get("original_input", payload)
        if issubclass(schema, Selection):
            sections = payload["sections"]
            data = Selection(
                angle="Explain Acme's measurement process.",
                ranked_sections=[RankedSection(section_id=s["section_id"], rank=n, reason="Relevant measurement evidence")
                                 for n, s in enumerate(sections, 1)],
                selected_section_ids=[s["section_id"] for s in sections[1:7]],
            )
        elif schema is Facts:
            sentences = [e for e in payload["evidence"] if ".s" in e["id"]]
            data = Facts(claims=[Claim(claim_id=f"claim_{n:03d}", text=e["text"], source_ids=[e["id"]],
                                      attribution="Acme", company_names=["Acme"])
                                 for n, e in enumerate(sentences, 1)])
        elif schema is Script:
            claims = payload["approved_claims"]

            def item(text, claim):
                return CitedText(text=text, claim_ids=[claim["claim_id"]], company_names=["Acme"])

            data = Script(title=item("Acme measurement", claims[0]), scenes=[
                Scene(scene_id=f"scene_{n:03d}", title=item("Acme measurement", claim),
                      claim_ids=[claim["claim_id"]], narration=[item(claim["text"], claim)],
                      on_screen=[item("Acme measurement", claim)], visual_direction="Reveal the baseline label.")
                for n, claim in enumerate((claims * 6)[:6], 1)
            ])
        else:
            data = Verdict(status=self.verdict, reason="Checked only the provided evidence.")
        if self.transform:
            data = self.transform(data)
        return data, {"resolved_model": model, "response_id": "fake_response", "usage": {"total_tokens": 10}}


@pytest.fixture
def article_path(tmp_path):
    blocks = [Block(id="block_0001", type="heading", order=1, section_path=["Guide"],
                    source_kind="original_html", source_locator="/h1", level=1, text="Guide")]
    for n in range(6):
        order = len(blocks) + 1
        section = ["Guide", f"Measurement {n + 1}"]
        blocks.append(Block(id=f"block_{order:04d}", order=order, type="heading", level=2,
                            text=section[-1], section_path=section, source_kind="original_html", source_locator=f"/h2[{n+1}]"))
        order += 1
        block_id = f"block_{order:04d}"
        blocks.append(Block(id=block_id, order=order, type="paragraph", text=LONG_SENTENCE,
                            sentences=split_sentences(LONG_SENTENCE, block_id), section_path=section,
                            source_kind="original_html", source_locator=f"/p[{n+1}]"))
    document = ArticleDocument(
        source=Source(requested_url="https://example.org/guide", final_url="https://example.org/guide",
                      retrieved_at="2026-11-08T00:00:00Z", html_sha256="a" * 64, snapshot_path="frozen.html"),
        extraction=Extraction(parser_name="fixture", parser_version="1", splitter_name="pysbd-en",
                              splitter_version="0.3.4", fallback_used=False),
        article=Article(title="Guide"), blocks=blocks,
        validation=Validation(status="valid", warnings=[], errors=[], counts={}),
    )
    path = tmp_path / "article.json"
    write_json(path, document)
    return path


@pytest.fixture
def setup_pipeline(article_path, tmp_path):
    provider = FakeProvider()
    config = PipelineConfig(publisher="Acme", company_aliases={"Acme": ["Acme's"]}, min_narration_words=300)
    pipeline = Pipeline(article_path, tmp_path / "output", tmp_path / "cache", config, provider)
    return pipeline, provider


@pytest.fixture
def real_index():
    from article_video.evidence import EvidenceIndex
    return EvidenceIndex.load(Path(__file__).resolve().parents[2] / "output" / "article.json")
