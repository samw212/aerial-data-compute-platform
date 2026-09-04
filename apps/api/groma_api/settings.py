"""Service configuration. Build spec 19.3.

Validated at start-up so a missing or malformed variable fails immediately rather
than on the first request that needs it. Every variable is prefixed GROMA_.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="GROMA_", env_file=os.environ.get("GROMA_ENV_FILE"), extra="ignore"
    )

    database_url: str = Field(description="postgresql+psycopg://user:pass@host/db")
    redis_url: str = "redis://127.0.0.1:6379/0"
    artefact_root: Path = Path("/root/autodl-tmp/groma/artefacts")
    nodeodm_url: str | None = None
    """Empty means the ODM backend reports available() = False."""
    colmap_bin: str | None = None
    default_srid: int = 2326
    jwt_secret: str = Field(min_length=32, description="Signs session cookies")
    max_upload_gb: float = 20.0
    kernel_max_cells: int = 2_000_000
    """Guard against a 0.05 m grid request."""
    session_hours: int = 24 * 7
    secure_cookies: bool = False
    """True behind HTTPS. AutoDL's custom-service link is plain HTTP."""
    public_url: str | None = None
    maps_provider: str = "hk-landsd"
    """hk-landsd (free, no key) | google (needs GROMA_MAPS_KEY)."""
    maps_key: str | None = None

    @field_validator("database_url")
    @classmethod
    def _must_be_postgres(cls, value: str) -> str:
        if not value.startswith("postgresql"):
            raise ValueError("GROMA_DATABASE_URL must be a postgresql:// URL")
        return value

    @field_validator("artefact_root")
    @classmethod
    def _absolute(cls, value: Path) -> Path:
        return value.expanduser().resolve()


@lru_cache
def get_settings() -> Settings:
    return Settings()


__all__ = ["Settings", "get_settings"]
