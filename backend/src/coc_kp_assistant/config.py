from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="COC_KP_",
        env_file=".env",
        extra="ignore",
    )

    app_name: str = "Local COC7 KP Assistant"
    app_version: str = "0.1.0"
    database_url: str = Field(
        default="sqlite:///./data/coc_kp.db",
        description="Dedicated application database URL.",
    )
    source_pack_root: Path = Path("./data/source-packs")
    vector_root: Path = Path("./data/vectors")
    allowed_origins: tuple[str, ...] = ("http://127.0.0.1:5180",)


@lru_cache
def get_settings() -> Settings:
    return Settings()
