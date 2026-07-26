from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import ConfigDict, Field, model_validator

from coc_kp_assistant.domain.base import DomainModel
from coc_kp_assistant.domain.campaigns import CampaignCreate, CampaignState
from coc_kp_assistant.domain.investigators import (
    InvestigatorBackstory,
    InvestigatorCondition,
    InvestigatorCreate,
    SkillEntry,
)
from coc_kp_assistant.domain.rolls import PercentileDice


class CampaignReplace(CampaignCreate):
    expected_version: int = Field(ge=1)


class CampaignResponse(CampaignState):
    pass


class InvestigatorReplace(InvestigatorCreate):
    expected_version: int = Field(ge=1)
    hit_points: int = Field(ge=0)
    magic_points: int = Field(ge=0)
    sanity: int = Field(ge=0, le=100)
    mythos: int = Field(default=0, ge=0, le=100)
    conditions: frozenset[InvestigatorCondition] = frozenset()

    @model_validator(mode="after")
    def validate_current_resources(self) -> "InvestigatorReplace":
        if self.hit_points > self.maximum_hit_points:
            raise ValueError("hit points exceed derived maximum")
        if self.magic_points > self.maximum_magic_points:
            raise ValueError("magic points exceed derived maximum")
        if self.sanity > 99 - self.mythos:
            raise ValueError("sanity exceeds the mythos-adjusted cap")
        return self


class InvestigatorResponse(InvestigatorCreate):
    investigator_id: UUID
    campaign_id: UUID
    hit_points: int
    magic_points: int
    sanity: int
    mythos: int
    conditions: frozenset[InvestigatorCondition]
    version: int


class SkillsReplace(DomainModel):
    expected_version: int = Field(ge=1)
    skills: tuple[SkillEntry, ...]

    @model_validator(mode="after")
    def unique_skill_identity(self) -> "SkillsReplace":
        identities = [(item.skill_key, item.specialization) for item in self.skills]
        if len(identities) != len(set(identities)):
            raise ValueError("skill key and specialization pairs must be unique")
        return self


class BackstoryReplace(DomainModel):
    expected_version: int = Field(ge=1)
    backstory: InvestigatorBackstory


class DifficultyLabel(StrEnum):
    REGULAR = "regular"
    HARD = "hard"
    EXTREME = "extreme"


class RecordedRollRequest(DomainModel):
    campaign_id: UUID
    investigator_id: UUID | None = None
    skill_key: str | None = Field(default=None, max_length=80)
    label: str = Field(min_length=1, max_length=160)
    target: int = Field(ge=0, le=100)
    difficulty: DifficultyLabel = DifficultyLabel.REGULAR
    bonus_penalty: int = Field(default=0, ge=-2, le=2)
    dice: PercentileDice | None = None

    @model_validator(mode="after")
    def validate_optional_dice(self) -> "RecordedRollRequest":
        if self.dice is not None and len(self.dice.tens_digits) != abs(self.bonus_penalty) + 1:
            raise ValueError("tens dice count must be one plus the bonus/penalty magnitude")
        return self


class RecordedRollResponse(DomainModel):
    roll_id: UUID
    campaign_id: UUID
    investigator_id: UUID | None
    skill_key: str | None
    label: str
    roll: int
    tens: tuple[int, ...]
    selected_tens: int
    ones: int
    target: int
    regular_threshold: int
    hard_threshold: int
    extreme_threshold: int
    outcome: str
    difficulty: DifficultyLabel
    bonus_penalty: int
    passed: bool
    created_at: datetime


class AuditResponse(DomainModel):
    audit_id: UUID
    campaign_id: UUID | None
    action: str
    entity_type: str
    entity_id: UUID
    expected_version: int | None
    before: dict[str, object] | None
    after: dict[str, object] | None
    created_at: datetime


class VersionedDeleteRequest(DomainModel):
    expected_version: int = Field(ge=1)


class RuleCitationResponse(DomainModel):
    model_config = ConfigDict(from_attributes=True)

    citation_id: str
    chunk_id: str
    excerpt: str
    score: float
    source_pack: str
    edition: str
    module: str
    era: tuple[str, ...]
    filename: str
    page: int | None
    section: str
    checksum: str


class RuleSearchResponse(DomainModel):
    query: str
    results: tuple[RuleCitationResponse, ...]


class RuleAnswerRequest(DomainModel):
    question: str = Field(min_length=1, max_length=1000)
    source_pack_ids: tuple[str, ...] = ()
    editions: tuple[str, ...] = ()
    modules: tuple[str, ...] = ()
    eras: tuple[str, ...] = ()
    limit: int = Field(default=8, ge=1, le=20)


class RuleAnswerResponse(DomainModel):
    question: str
    answer: str
    citations: tuple[RuleCitationResponse, ...]
    abstained: bool
    reason: str | None
