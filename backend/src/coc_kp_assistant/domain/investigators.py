from enum import StrEnum
from uuid import UUID

from pydantic import Field, model_validator

from .base import DomainModel


class InvestigatorCondition(StrEnum):
    MAJOR_WOUND = "major_wound"
    UNCONSCIOUS = "unconscious"
    DYING = "dying"
    STABILIZED = "stabilized"
    DEAD = "dead"
    BOUT_OF_MADNESS = "bout_of_madness"
    TEMPORARY_INSANITY = "temporary_insanity"
    INDEFINITE_INSANITY = "indefinite_insanity"


class CoreCharacteristics(DomainModel):
    strength: int = Field(ge=0, le=200)
    constitution: int = Field(ge=0, le=200)
    size: int = Field(ge=0, le=200)
    dexterity: int = Field(ge=0, le=200)
    appearance: int = Field(ge=0, le=200)
    intelligence: int = Field(ge=0, le=200)
    power: int = Field(ge=0, le=200)
    education: int = Field(ge=0, le=200)


class SkillEntry(DomainModel):
    skill_key: str = Field(min_length=1, max_length=80)
    display_name: str = Field(min_length=1, max_length=100)
    specialization: str | None = Field(default=None, max_length=100)
    base_value: int = Field(ge=0, le=100)
    current_value: int = Field(ge=0, le=100)
    improvement_mark: bool = False
    source_pack_id: str | None = Field(default=None, max_length=80)

    @property
    def half_value(self) -> int:
        return self.current_value // 2

    @property
    def fifth_value(self) -> int:
        return self.current_value // 5


class InvestigatorBackstory(DomainModel):
    personal_description: tuple[str, ...] = ()
    ideology_and_beliefs: tuple[str, ...] = ()
    significant_people: tuple[str, ...] = ()
    meaningful_locations: tuple[str, ...] = ()
    treasured_possessions: tuple[str, ...] = ()
    traits: tuple[str, ...] = ()
    injuries_and_scars: tuple[str, ...] = ()
    phobias_and_manias: tuple[str, ...] = ()
    mythos_tomes_spells_artifacts: tuple[str, ...] = ()
    strange_encounters: tuple[str, ...] = ()


class InvestigatorCreate(DomainModel):
    name: str = Field(min_length=1, max_length=160)
    player_name: str | None = Field(default=None, max_length=160)
    occupation: str = Field(min_length=1, max_length=160)
    age: int = Field(ge=15, le=120)
    gender: str | None = Field(default=None, max_length=80)
    residence: str | None = Field(default=None, max_length=200)
    birthplace: str | None = Field(default=None, max_length=200)
    era: str = Field(default="1920s", min_length=1, max_length=80)
    characteristics: CoreCharacteristics
    luck: int = Field(ge=0, le=100)
    move_rate: int = Field(ge=0, le=20)
    damage_bonus: str = Field(default="0", min_length=1, max_length=40)
    build: int = Field(default=0, ge=-5, le=20)
    credit_rating: int = Field(default=0, ge=0, le=100)
    spending_level: str | None = Field(default=None, max_length=120)
    cash: str | None = Field(default=None, max_length=120)
    assets: str | None = Field(default=None, max_length=1000)
    skills: tuple[SkillEntry, ...] = ()
    backstory: InvestigatorBackstory = InvestigatorBackstory()

    @model_validator(mode="after")
    def unique_skill_identity(self) -> "InvestigatorCreate":
        identities = [(item.skill_key, item.specialization) for item in self.skills]
        if len(identities) != len(set(identities)):
            raise ValueError("skill key and specialization pairs must be unique")
        return self

    @property
    def maximum_hit_points(self) -> int:
        return (self.characteristics.constitution + self.characteristics.size) // 10

    @property
    def maximum_magic_points(self) -> int:
        return self.characteristics.power // 5

    @property
    def starting_sanity(self) -> int:
        return self.characteristics.power


class InvestigatorState(DomainModel):
    investigator_id: UUID
    campaign_id: UUID
    profile: InvestigatorCreate
    hit_points: int = Field(ge=0)
    magic_points: int = Field(ge=0)
    sanity: int = Field(ge=0, le=100)
    mythos: int = Field(default=0, ge=0, le=100)
    conditions: frozenset[InvestigatorCondition] = frozenset()
    version: int = Field(default=1, ge=1)

    @model_validator(mode="after")
    def state_within_derived_limits(self) -> "InvestigatorState":
        if self.hit_points > self.profile.maximum_hit_points:
            raise ValueError("hit points exceed derived maximum")
        if self.magic_points > self.profile.maximum_magic_points:
            raise ValueError("magic points exceed derived maximum")
        if self.sanity > 99 - self.mythos:
            raise ValueError("sanity exceeds the mythos-adjusted cap")
        return self
