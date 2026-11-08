"""Strict model outputs; provenance and human decisions are added locally."""
from typing import Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class RankedSection(Model):
    section_id: str = Field(min_length=1)
    rank: int = Field(ge=1)
    reason: str = Field(min_length=1)


class Selection(Model):
    angle: str = Field(min_length=1)
    ranked_sections: list[RankedSection] = Field(min_length=1)
    selected_section_ids: list[str] = Field(min_length=1, max_length=7)


class Claim(Model):
    claim_id: str = Field(pattern=r"^claim_[a-zA-Z0-9_]+$")
    text: str = Field(min_length=1)
    source_ids: list[str] = Field(min_length=1)
    attribution: str = Field(min_length=1)
    # Supplement the deterministic name detector; these are never its sole input.
    company_names: list[str]


class Facts(Model):
    claims: list[Claim] = Field(min_length=1)


class CitedText(Model):
    text: str = Field(min_length=1)
    claim_ids: list[str] = Field(min_length=1)
    company_names: list[str]


class Scene(Model):
    scene_id: str = Field(pattern=r"^scene_[a-zA-Z0-9_]+$")
    title: CitedText
    claim_ids: list[str] = Field(min_length=1)
    narration: list[CitedText] = Field(min_length=1)
    on_screen: list[CitedText]
    visual_direction: str = Field(min_length=1)


class Script(Model):
    title: CitedText
    scenes: list[Scene] = Field(min_length=6, max_length=8)


class Verdict(Model):
    status: Literal["supported", "partial", "unsupported"]
    reason: str = Field(min_length=1)


class ReviewItem(Model):
    id: str
    code: str
    target: str
    message: str


class RunInfo(Model):
    requested_model: str
    resolved_model: str
    prompt_version: str
    cache_key: str
    response_id: str | None
    usage: dict[str, int]


class Check(Model):
    target: str
    text_sha256: str
    verdict: Verdict
    run: RunInfo


class ScriptQualityReview(Model):
    version: str
    artifact_sha256: str
    method: Literal["deterministic"] = "deterministic"
    categories: list[str]
    flags: list[ReviewItem]


class Review(Model):
    stage: Literal["selection", "facts", "script"]
    artifact_sha256: str
    errors: list[ReviewItem]
    flags: list[ReviewItem]
    checks: list[Check]
    quality: ScriptQualityReview | None = Field(default=None, exclude_if=lambda value: value is None)


T = TypeVar("T", bound=Model)


class Artifact(Model, Generic[T]):
    schema_version: Literal["1.0"] = "1.0"
    stage: Literal["selection", "facts", "script"]
    inputs: dict[str, str]
    run: RunInfo
    data: T


class Approval(Model):
    # Omit the legacy human default so existing receipt hashes remain valid.
    mode: Literal["human", "automatic"] = Field(default="human", exclude_if=lambda value: value == "human")
    stage: Literal["selection", "facts", "script"]
    artifact_sha256: str
    review_sha256: str
    reviewer: str = Field(min_length=1)
    reviewed_at: str
    note: str
    accepted_review_items: list[str]
    approved_claim_ids: list[str]


class PipelineConfig(Model):
    # Explicit snapshots are a reproducible baseline, not a 'latest model' alias.
    generation_model: str = Field(default="gpt-4.1-mini-2025-04-14", min_length=1)
    verifier_model: str = Field(default="gpt-4.1-2025-04-14", min_length=1)
    publisher: str = Field(default="Searchbloom", min_length=1)
    company_aliases: dict[str, list[str]] = Field(default_factory=lambda: {
        "Searchbloom": ["Search Bloom"],
        "The SEO Works": ["SEO Works"],
        "iPullRank": ["i Pull Rank"],
        "OpenAI": ["Open AI"],
    })
    min_narration_words: int = Field(default=350, ge=1)
    max_narration_words: int = Field(default=450, ge=1)
    max_output_tokens: int = Field(default=14000, ge=1)
