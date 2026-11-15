"""Pydantic v2 schemas — the single source of truth for episodes, skills,
working-memory items, provenance and sleep reports. Strict by construction:
unknown fields are rejected so nothing silently drifts."""
from __future__ import annotations
from enum import Enum
from typing import Any, Literal, Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator


class Source(str, Enum):
    user_instruction = "user_instruction"
    verified_execution = "verified_execution"
    visual_inspection = "visual_inspection"
    documentation = "documentation"
    training_data = "training_data"
    unverified_hypothesis = "unverified_hypothesis"


class VerificationStatus(str, Enum):
    VERIFIED = "VERIFIED"
    UNVERIFIED = "UNVERIFIED"
    FAILED = "FAILED"


class Modality(str, Enum):
    text = "text"
    code = "code"
    vision = "vision"
    mixed = "mixed"


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", use_enum_values=True)


class WorkingMemoryItem(StrictModel):
    id: str
    content: str
    modality: Modality = Modality.text
    priority: float = Field(default=0.5, ge=0.0, le=1.0)
    pinned: bool = False
    source: Source = Source.user_instruction
    created_at: str
    last_access: str
    token_estimate: int = 0
    meta: dict[str, Any] = Field(default_factory=dict)


class Episode(StrictModel):
    id: str
    situation: str
    modality: Modality = Modality.text
    objective: str = ""
    actions: list[str] = Field(default_factory=list)
    result: str = ""
    verification_status: VerificationStatus = VerificationStatus.UNVERIFIED
    mistakes: list[str] = Field(default_factory=list)
    lessons: list[str] = Field(default_factory=list)
    source: Source = Source.user_instruction
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    access_count: int = 0
    created_at: str
    updated_at: str
    archived: bool = False
    tags: list[str] = Field(default_factory=list)
    meta: dict[str, Any] = Field(default_factory=dict)


class VerificationStep(StrictModel):
    name: str
    command: str
    exit_code: int
    output_sha256: str
    passed: bool


class Skill(StrictModel):
    """A parameterized, verified, re-usable procedure. Only VERIFIED skills
    are ever compiled into training shards."""
    id: str
    name: str
    description: str
    domain: str = "general"           # python / web / css / debugging / chat / ...
    inputs: dict[str, str] = Field(default_factory=dict)   # param -> description
    reasoning_trace: list[str] = Field(default_factory=list)
    tool_calls: list[dict[str, Any]] = Field(default_factory=list)
    verification: list[VerificationStep] = Field(default_factory=list)
    final_output: str = ""
    source: Source = Source.verified_execution
    verification_status: VerificationStatus = VerificationStatus.UNVERIFIED
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    created_at: str
    updated_at: str
    times_used: int = 0
    meta: dict[str, Any] = Field(default_factory=dict)

    @property
    def verification_hash(self) -> str:
        from .util import content_hash
        return content_hash([s.model_dump() for s in self.verification])


class TrainingExample(StrictModel):
    """One JSONL line in a compiled shard."""
    id: str
    skill_id: str
    kind: Literal["instruction", "chain_of_thought", "synthetic_variation", "edge_case"]
    messages: list[dict[str, str]]
    provenance: dict[str, Any]

    @field_validator("messages")
    @classmethod
    def _nonempty(cls, v: list[dict[str, str]]) -> list[dict[str, str]]:
        if not v:
            raise ValueError("messages must not be empty")
        for m in v:
            if set(m) - {"role", "content"} or "role" not in m or "content" not in m:
                raise ValueError("each message needs exactly role+content")
        return v


class SleepReport(StrictModel):
    id: str
    started_at: str
    finished_at: str
    trigger: str
    episodes_reviewed: int = 0
    lessons_consolidated: int = 0
    concepts_linked: int = 0
    duplicates_merged: int = 0
    conflicts_flagged: int = 0
    episodes_archived: int = 0
    skills_compiled: int = 0
    skills_reverified: int = 0
    shard_path: Optional[str] = None
    shard_examples: int = 0
    shard_sha256: Optional[str] = None
    github_dispatch: str = "not_configured"   # dispatched / pending_dispatch / not_configured / failed
    weakness_domains: list[str] = Field(default_factory=list)
    unresolved: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
