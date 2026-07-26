from datetime import datetime
from enum import StrEnum
from typing import Any
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


class SourcePackSelectionReplace(DomainModel):
    expected_version: int = Field(ge=1)
    enabled_source_pack_ids: tuple[str, ...] = ()


class BackupCreateRequest(DomainModel):
    destination: str | None = Field(default=None, max_length=2000)


class BackupVerifyRequest(DomainModel):
    path: str = Field(min_length=1, max_length=2000)


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
    case_session_id: UUID | None = None
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
    case_session_id: UUID | None
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


class EngineCitationResponse(DomainModel):
    citation_id: str
    source_pack_id: str
    filename: str
    page: int
    section: str
    edition: str
    module: str
    era: tuple[str, ...]
    checksum: str


class SanityLossRequest(DomainModel):
    expected_version: int = Field(ge=1)
    loss: int = Field(ge=0, le=100)
    reason: str = Field(min_length=1, max_length=300)
    session_key: str | None = Field(default=None, max_length=120)
    case_session_id: UUID
    intelligence_roll_id: UUID | None = None


class InjuryRequest(DomainModel):
    expected_version: int = Field(ge=1)
    damage: int = Field(ge=1, le=100)
    reason: str = Field(min_length=1, max_length=300)
    session_key: str | None = Field(default=None, max_length=120)
    case_session_id: UUID


class RecoveryRequest(DomainModel):
    expected_version: int = Field(ge=1)
    care_type: str = Field(pattern=r"^(first_aid|medicine|natural)$")
    injury_id: UUID
    healing_roll: int | None = Field(default=None, ge=1, le=3)
    medicine_roll_id: UUID | None = None
    first_aid_roll_id: UUID | None = None
    constitution_roll_id: UUID | None = None
    period_key: str | None = Field(default=None, min_length=1, max_length=120)
    session_key: str | None = Field(default=None, max_length=120)
    case_session_id: UUID

    @model_validator(mode="after")
    def recovery_requires_healing_roll(self) -> "RecoveryRequest":
        if self.care_type in {"medicine", "natural"} and self.healing_roll is None:
            raise ValueError("medicine and natural recovery require a 1-3 healing roll")
        return self


class DyingCheckRequest(DomainModel):
    expected_version: int = Field(ge=1)
    constitution_roll_id: UUID
    period_key: str = Field(min_length=1, max_length=120)
    session_key: str | None = Field(default=None, max_length=120)
    case_session_id: UUID


class InsanityTransitionRequest(DomainModel):
    expected_version: int = Field(ge=1)
    transition: str = Field(pattern=r"^(bout_started|bout_ended|recovered)$")
    period_key: str | None = Field(default=None, min_length=1, max_length=120)
    evidence: str | None = Field(default=None, min_length=1, max_length=500)
    treatment_roll_id: UUID | None = None
    session_key: str | None = Field(default=None, max_length=120)
    case_session_id: UUID


class CombatRequest(DomainModel):
    attacker_id: UUID
    target_id: UUID
    target_expected_version: int = Field(ge=1)
    attack_roll_id: UUID
    weapon_key: str = Field(min_length=1, max_length=80)
    rolled_damage: int = Field(ge=0, le=100)
    session_key: str | None = Field(default=None, max_length=120)
    case_session_id: UUID

    @model_validator(mode="after")
    def distinct_participants(self) -> "CombatRequest":
        if self.attacker_id == self.target_id:
            raise ValueError("attacker and target must be distinct")
        return self


class EngineOperationResponse(DomainModel):
    operation_id: UUID
    operation_type: str
    investigator: InvestigatorResponse
    target: InvestigatorResponse | None = None
    citation: EngineCitationResponse
    citations: tuple[EngineCitationResponse, ...]
    loss: int | None = None
    sanity_before: int | None = None
    session_sanity_loss: int | None = None
    reason: str | None = None
    damage_applied: int | None = None
    injury_id: UUID | None = None
    healed: int | None = None
    care_type: str | None = None
    hit: bool | None = None
    weapon_key: str | None = None
    attack_roll_id: UUID | None = None
    passed: bool | None = None
    period_key: str | None = None
    terminal: bool | None = None
    stabilized: bool | None = None
    transition: str | None = None
    evidence: str | None = None
    created_at: datetime


class WeaponPolicyResponse(DomainModel):
    weapon_key: str
    name: str
    damage_notation: str
    maximum_rolled_damage: int
    skill_key: str
    uses_damage_bonus: bool
    citation: EngineCitationResponse
    citations: tuple[EngineCitationResponse, ...]


class ChaseParticipant(DomainModel):
    investigator_id: UUID
    role: str = Field(pattern=r"^(pursuer|fleeing)$")
    position: int = Field(default=0, ge=0, le=10000)


class ChaseParticipantState(ChaseParticipant):
    move_rate: int = Field(ge=1, le=20)
    actions_remaining: int = Field(ge=0, le=20)


class ChaseCreateRequest(DomainModel):
    title: str = Field(min_length=1, max_length=200)
    session_key: str | None = Field(default=None, max_length=120)
    case_session_id: UUID
    participants: tuple[ChaseParticipant, ...] = Field(min_length=2, max_length=20)
    escape_distance: int = Field(default=10, ge=1, le=10000)
    track_length: int = Field(default=10, ge=1, le=10000)

    @model_validator(mode="after")
    def unique_participants(self) -> "ChaseCreateRequest":
        ids = [item.investigator_id for item in self.participants]
        if len(ids) != len(set(ids)):
            raise ValueError("chase participants must be unique")
        if self.escape_distance > self.track_length:
            raise ValueError("escape distance must not exceed track length")
        if any(item.position > self.track_length for item in self.participants):
            raise ValueError("initial participant position must not exceed track length")
        return self


class ChaseAction(DomainModel):
    investigator_id: UUID
    action: str = Field(pattern=r"^(move|hazard)$")
    roll_id: UUID | None = None
    skill_key: str | None = Field(default=None, min_length=1, max_length=120)

    @model_validator(mode="after")
    def hazard_requires_roll(self) -> "ChaseAction":
        if self.action == "hazard" and (self.roll_id is None or self.skill_key is None):
            raise ValueError("hazard action requires roll_id and skill_key")
        return self


class ChaseAdvanceRequest(DomainModel):
    expected_version: int = Field(ge=1)
    action: ChaseAction


class ChaseResponse(DomainModel):
    chase_id: UUID
    campaign_id: UUID
    title: str
    case_session_id: UUID
    session_key: str | None
    status: str
    participants: tuple[ChaseParticipantState, ...]
    round: int
    escape_distance: int
    track_length: int
    version: int
    citation: EngineCitationResponse
    citations: tuple[EngineCitationResponse, ...]
    created_at: datetime
    updated_at: datetime


class RuleOperationLogResponse(DomainModel):
    operation_id: UUID
    campaign_id: UUID
    subject_id: UUID
    case_session_id: UUID | None
    session_key: str | None
    operation_type: str
    input_data: dict[str, Any]
    output_data: dict[str, Any]
    citation: EngineCitationResponse
    citations: tuple[EngineCitationResponse, ...]
    created_at: datetime
