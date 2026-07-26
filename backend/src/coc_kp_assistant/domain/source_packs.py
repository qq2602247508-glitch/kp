from enum import StrEnum
from typing import Literal

from pydantic import Field, field_validator

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
    priority: int = Field(default=100, ge=0, le=1000)
    default_enabled: bool = False
    eras: tuple[str, ...] = ()
    files: tuple[SourceFileManifest, ...] = ()
    notes: str | None = Field(default=None, max_length=2000)

