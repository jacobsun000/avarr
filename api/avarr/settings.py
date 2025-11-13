"""Application configuration loaded from environment variables."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import List, Optional

from pydantic import Field, HttpUrl
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings with sane defaults for local development."""

    database_url: str = Field(
        default="sqlite:///./storage.db",
        description="SQLAlchemy connection string for persistence",
    )
    download_root: Path = Field(
        default=Path("downloads"), description="Folder where assets are stored"
    )
    telegram_bot_token: Optional[str] = Field(
        default=None, description="Bot token used for sending Telegram updates"
    )
    telegram_webhook_secret: Optional[str] = Field(
        default=None,
        description="Shared token validated via X-Telegram-Bot-Api-Secret-Token",
    )
    base_external_url: Optional[HttpUrl] = Field(
        default=None,
        description="Public URL used inside Telegram notifications",
    )
    allowed_source_domains: List[str] = Field(
        default_factory=list,
        description="Optional whitelist of hostnames allowed for download requests",
    )
    notifier_min_percent_step: float = Field(
        default=10.0,
        description="Minimum percentage delta before pushing Telegram progress updates",
    )
    max_concurrent_downloads: int = Field(
        default=1,
        ge=1,
        le=10,
        description="Maximum number of simultaneous downloads (1-10)",
    )
    transcode_workers: int = Field(
        default=1,
        ge=1,
        le=4,
        description="Number of parallel ffmpeg jobs for MP4 transcoding",
    )

    model_config = SettingsConfigDict(env_prefix="AVARR_")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached Settings instance."""

    settings = Settings()
    settings.download_root = Path(settings.download_root).expanduser().resolve()
    settings.download_root.mkdir(parents=True, exist_ok=True)
    return settings


__all__ = ["Settings", "get_settings"]
