from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import Field

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


class CaseEntryCreate(DomainModel):
    title: str = Field(min_length=1, max_length=200)
    player_visible_text: str = Field(default="", max_length=20_000)
    keeper_truth: str = Field(default="", max_length=20_000)
    status: str = Field(default="active", min_length=1, max_length=40)
    time_label: str | None = Field(default=None, max_length=120)
    role: str | None = Field(default=None, max_length=120)
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
