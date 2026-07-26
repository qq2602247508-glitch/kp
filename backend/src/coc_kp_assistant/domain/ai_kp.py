from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import Field, model_validator

from .base import DomainModel
from .case_state import CaseEntityKind

AIKPMode = Literal["answer", "private_hint", "scenario_draft"]
ProposalType = Literal["case_state_create", "case_state_replace"]
ProposalStatus = Literal["pending", "confirmed", "rejected"]


class AIKPRequest(DomainModel):
    question: str = Field(min_length=1, max_length=8_000)
    mode: AIKPMode = "private_hint"


class AIKPResponseDraft(DomainModel):
    answer: str = Field(default="", max_length=20_000)
    keeper_private_hints: tuple[str, ...] = Field(default=(), max_length=20)
    scene_suggestions: tuple[str, ...] = Field(default=(), max_length=20)
    citation_ids: tuple[str, ...] = Field(default=(), max_length=20)


class AIKPProposalDraft(DomainModel):
    proposal_type: ProposalType
    case_kind: CaseEntityKind
    target_entity_id: UUID | None = None
    expected_entity_version: int | None = Field(default=None, ge=1)
    payload: dict[str, Any]
    citation_ids: tuple[str, ...] = Field(default=(), max_length=20)

    @model_validator(mode="after")
    def validate_action_identity(self) -> "AIKPProposalDraft":
        if self.proposal_type == "case_state_create":
            if self.target_entity_id is not None or self.expected_entity_version is not None:
                raise ValueError("create proposal cannot target an existing entity")
        elif self.target_entity_id is None or self.expected_entity_version is None:
            raise ValueError("replace proposal requires target entity and version")
        return self


class AIKPDraft(DomainModel):
    response: AIKPResponseDraft
    proposals: tuple[AIKPProposalDraft, ...] = Field(default=(), max_length=30)


class AIProposalResponse(DomainModel):
    proposal_id: UUID
    campaign_id: UUID
    proposal_type: ProposalType
    case_kind: CaseEntityKind
    target_entity_id: UUID | None
    campaign_version: int
    target_version: int | None
    payload: dict[str, Any]
    diff: dict[str, dict[str, Any]]
    evidence: tuple[dict[str, Any], ...]
    citation_ids: tuple[str, ...]
    model_name: str
    model_metadata: dict[str, Any]
    status: ProposalStatus
    version: int
    rejection_reason: str | None
    applied_entity_id: UUID | None
    created_at: datetime
    expires_at: datetime
    is_expired: bool
    resolved_at: datetime | None


class AIKPResponse(DomainModel):
    answer: str
    keeper_private_hints: tuple[str, ...]
    scene_suggestions: tuple[str, ...]
    citations: tuple[dict[str, Any], ...]
    proposals: tuple[AIProposalResponse, ...]
    model_name: str
    advisory_only: Literal[True] = True


class ProposalDecision(DomainModel):
    expected_version: int = Field(ge=1)
    decision: Literal["confirm", "reject"]
    reason: str | None = Field(default=None, max_length=2_000)

    @model_validator(mode="after")
    def rejection_requires_reason(self) -> "ProposalDecision":
        if self.decision == "reject" and not (self.reason or "").strip():
            raise ValueError("rejection requires a reason")
        return self
