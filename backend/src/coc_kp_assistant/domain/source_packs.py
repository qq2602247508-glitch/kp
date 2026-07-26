from enum import StrEnum
from typing import Literal

from pydantic import Field, StrictBool, StrictInt, field_validator, model_validator

from .base import DomainModel


class SourcePackKind(StrEnum):
    CORE = "core"
    INVESTIGATOR = "investigator"
    QUICKSTART = "quickstart"
    CARD_DECK = "card_deck"
    MAGIC = "magic"
    ERA = "era"
    SETTING = "setting"
    LEGACY = "legacy"


class SourcePackStatus(StrEnum):
    REGISTERED = "registered"
    INDEXING = "indexing"
    READY = "ready"
    FAILED = "failed"


class SourceFileManifest(DomainModel):
    relative_path: str = Field(min_length=1)
    media_type: str = Field(min_length=1)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    page_count: int | None = Field(default=None, ge=1)

    @field_validator("relative_path")
    @classmethod
    def require_relative_path(cls, value: str) -> str:
        if value.startswith("/") or ".." in value.split("/"):
            raise ValueError("source file path must stay inside its source pack")
        return value


class SourcePackManifest(DomainModel):
    pack_id: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]{2,79}$")
    ruleset: Literal["coc7e"] = "coc7e"
    title: str = Field(min_length=1, max_length=200)
    version: str = Field(min_length=1, max_length=40)
    edition: str = Field(default="7e", min_length=1, max_length=40)
    kind: SourcePackKind
    status: SourcePackStatus = SourcePackStatus.REGISTERED
    priority: StrictInt = Field(default=100, ge=0, le=1000)
    default_enabled: StrictBool = False
    eras: tuple[str, ...] = ()
    files: tuple[SourceFileManifest, ...] = ()
    notes: str | None = Field(default=None, max_length=2000)

    @field_validator("eras", mode="before")
    @classmethod
    def require_string_era_array(cls, value: object) -> object:
        if not isinstance(value, (list, tuple)) or any(
            not isinstance(item, str) or not item.strip() for item in value
        ):
            raise ValueError("eras must be an array of non-empty strings")
        return value

    @model_validator(mode="after")
    def enforce_coc_namespace_and_edition(self) -> "SourcePackManifest":
        lowered_identity = " ".join(
            (self.pack_id, self.title, self.version, self.edition, self.kind.value)
        ).lower()
        foreign_markers = ("".join(("d", "n", "d")), "d&d", "5e")
        if any(marker in lowered_identity for marker in foreign_markers):
            raise ValueError("D&D/5e source packs are forbidden")
        if self.pack_id.startswith("coc-classic."):
            if (
                self.kind is not SourcePackKind.LEGACY
                or self.edition != "classic-40th"
                or self.default_enabled
                or self.priority < 900
            ):
                raise ValueError("classic source packs must be isolated legacy packs")
        elif self.pack_id.startswith("coc7e."):
            if self.kind is SourcePackKind.LEGACY or self.edition not in {
                "7e",
                "7e-supplement",
            }:
                raise ValueError("coc7e source packs must use a seventh-edition identity")
        else:
            raise ValueError("source pack must use an approved COC namespace")
        return self
