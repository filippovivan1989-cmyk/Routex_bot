"""Configuration module for RouteX VPN bot."""

from __future__ import annotations

from functools import lru_cache
from typing import List

from pydantic import BaseSettings, Field, HttpUrl, validator


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    bot_token: str = Field(..., alias="BOT_TOKEN")
    admin_ids: List[int] = Field(..., alias="ADMIN_IDS")
    tz: str = Field("Europe/Helsinki", alias="TZ")
    cloudtips_link: HttpUrl = Field(..., alias="CLOUDTIPS_LINK")
    panel_url: str = Field(..., alias="PANEL_URL")
    panel_login: str = Field(..., alias="PANEL_LOGIN")
    panel_password: str = Field(..., alias="PANEL_PASSWORD")
    panel_inbound_id: int = Field(..., alias="PANEL_INBOUND_ID")
    events_webhook_token: str = Field(..., alias="EVENTS_WEBHOOK_TOKEN")
    webhook_url: str | None = Field(None, alias="WEBHOOK_URL")
    host: str = Field("0.0.0.0", alias="HOST")
    port: int = Field(8080, alias="PORT")
    database_path: str = Field("./data/routex.sqlite3", alias="DATABASE_PATH")
    batch_size: int = Field(30, alias="BATCH_SIZE")
    batch_delay_seconds: float = Field(1.5, alias="BATCH_DELAY_SECONDS")
    guide_url: str = Field("https://telegra.ph/RouteX-VPN-Guide-01-01", alias="GUIDE_URL")

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False

    @validator("admin_ids", pre=True)
    def parse_admin_ids(cls, value: str | List[int]) -> List[int]:
        if isinstance(value, list):
            return [int(v) for v in value]
        return [int(item.strip()) for item in value.split(",") if item.strip()]


@lru_cache
def get_settings() -> Settings:
    """Return cached application settings."""

    return Settings()  # type: ignore[arg-type]


__all__ = ["Settings", "get_settings"]
