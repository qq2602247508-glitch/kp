from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import Field, model_validator

from .base import DomainModel


class CaseEntityKind(StrEnum):
    SESSIONS = "sessions"
    PEOPLE = "people"
    LOCATIONS = "locations"
    SCENES = "scenes"
    CLUES = "clues"
    RELATIONSHIPS = "relationships"
    HANDOUTS = "handouts"
    TIMELINE_EVENTS = "timeline-events"


class PersonEntityType(StrEnum):
    KEEPER_NPC = "keeper_npc"
    MYTHOS_ENTITY = "mythos_entity"
    ANIMAL = "animal"
    CUSTOM = "custom"


class PersonCharacteristics(DomainModel):
    strength: int = Field(default=50, ge=0, le=999)
    constitution: int = Field(default=50, ge=0, le=999)
    size: int = Field(default=50, ge=0, le=999)
    dexterity: int = Field(default=50, ge=0, le=999)
    intelligence: int = Field(default=50, ge=0, le=999)
    power: int = Field(default=50, ge=0, le=999)
    appearance: int = Field(default=50, ge=0, le=999)
    education: int = Field(default=50, ge=0, le=999)


class PersonSkill(DomainModel):
    name: str = Field(min_length=1, max_length=120)
    value: int = Field(ge=0, le=999)
    description: str = Field(default="", max_length=1000)


class PersonAttack(DomainModel):
    name: str = Field(min_length=1, max_length=120)
    skill_name: str = Field(min_length=1, max_length=120)
    skill_value: int = Field(ge=0, le=999)
    damage: str = Field(min_length=1, max_length=120)
    attacks_per_round: int = Field(default=1, ge=1, le=20)
    range: str | None = Field(default=None, max_length=120)
    malfunction: int | None = Field(default=None, ge=0, le=100)
    description: str = Field(default="", max_length=1000)


class CaseEntryCreate(DomainModel):
    title: str = Field(min_length=1, max_length=200)
    player_visible_text: str = Field(default="", max_length=20_000)
    keeper_truth: str = Field(default="", max_length=20_000)
    status: str = Field(default="active", min_length=1, max_length=40)
    time_label: str | None = Field(default=None, max_length=120)
    role: str | None = Field(default=None, max_length=120)
    person_type: PersonEntityType = PersonEntityType.KEEPER_NPC
    characteristics: PersonCharacteristics | None = None
    hit_points: int | None = Field(default=None, ge=0, le=999)
    move_rate: int | None = Field(default=None, ge=0, le=99)
    damage_bonus: str | None = Field(default=None, max_length=40)
    build: int | None = Field(default=None, ge=-10, le=20)
    armor: str | None = Field(default=None, max_length=200)
    sanity_loss: str | None = Field(default=None, max_length=120)
    skills: tuple[PersonSkill, ...] = ()
    attacks: tuple[PersonAttack, ...] = ()
    special_abilities: tuple[str, ...] = ()
    session_id: UUID | None = None
    location_id: UUID | None = None
    scene_id: UUID | None = None
    person_id: UUID | None = None
    clue_id: UUID | None = None
    source_clue_id: UUID | None = None
    target_clue_id: UUID | None = None
    relationship_type: str | None = Field(default=None, max_length=80)
    discovered: bool = False
    revealed: bool = False
    sort_order: int = Field(default=0, ge=-100_000, le=100_000)

    @model_validator(mode="after")
    def validate_person_sheet(self) -> "CaseEntryCreate":
        skill_names = [skill.name.casefold() for skill in self.skills]
        if len(skill_names) != len(set(skill_names)):
            raise ValueError("person skill names must be unique")
        if len(self.special_abilities) > 50:
            raise ValueError("a person may have at most 50 special abilities")
        return self


class CaseEntryReplace(CaseEntryCreate):
    expected_version: int = Field(ge=1)


class CaseEntryResponse(CaseEntryCreate):
    entity_id: UUID
    campaign_id: UUID
    kind: CaseEntityKind
    version: int
    created_at: datetime
    updated_at: datetime


class PlayerCaseEntryResponse(DomainModel):
    entity_id: UUID
    campaign_id: UUID
    kind: CaseEntityKind
    title: str
    player_visible_text: str
    status: str
    time_label: str | None = None
    role: str | None = None
    discovered: bool = False
    revealed: bool = False
