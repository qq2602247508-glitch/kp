from enum import StrEnum
from typing import Literal
from uuid import UUID, uuid4

from pydantic import Field

from .base import DomainModel


class CampaignEra(StrEnum):
    ANCIENT = "ancient"
    DARK_AGES = "dark_ages"
    GASLIGHT = "gaslight"
    NINETEEN_TWENTIES = "1920s"
    MODERN = "modern"
    FUTURE = "future"
    APOCALYPSE = "apocalypse"
    DREAMLANDS = "dreamlands"
    CUSTOM = "custom"


class CampaignCreate(DomainModel):
    title: str = Field(min_length=1, max_length=200)
    ruleset: Literal["coc7e"] = "coc7e"
    era: CampaignEra = CampaignEra.NINETEEN_TWENTIES
    custom_era_label: str | None = Field(default=None, max_length=100)
    in_world_date: str | None = Field(default=None, max_length=100)
    starting_location: str | None = Field(default=None, max_length=200)
    enabled_source_pack_ids: tuple[str, ...] = ()
    house_rules: tuple[str, ...] = ()
    keeper_notes: str | None = Field(default=None, max_length=10_000)


class CampaignState(CampaignCreate):
    campaign_id: UUID = Field(default_factory=uuid4)
    version: int = Field(default=1, ge=1)

