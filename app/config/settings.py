"""Application settings — singleton Pydantic Settings.

All configuration is read from environment variables / .env exactly once
and exposed through the cached `get_settings()` accessor (and the `settings`
module-level singleton). Every other module imports configuration from here
so we have a single source of truth.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import List, Literal

from dotenv import load_dotenv
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Load .env into os.environ once, before any sub-settings class is constructed.
# Without this, pydantic-settings would only inject .env values into the
# top-level Settings model — the nested AppSettings/OpenAISettings/etc.
# constructed via `default_factory` would only see actual os.environ values.
load_dotenv(override=False)


class AppSettings(BaseSettings):
    name: str = Field(default="Voice Diagnostic Agent", alias="APP_NAME")
    env: Literal["development", "staging", "production"] = Field(
        default="development", alias="APP_ENV"
    )
    host: str = Field(default="0.0.0.0", alias="APP_HOST")
    port: int = Field(default=8000, alias="APP_PORT")
    public_url: str = Field(
        default="http://localhost:8000",
        alias="APP_PUBLIC_URL",
        description="Publicly reachable URL — Twilio webhooks call back here.",
    )
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    model_config = SettingsConfigDict(extra="ignore", populate_by_name=True)


class DatabaseSettings(BaseSettings):
    url: str = Field(
        default="sqlite+aiosqlite:///./data/voice_ai.db", alias="DATABASE_URL"
    )
    echo: bool = Field(default=False, alias="DATABASE_ECHO")

    model_config = SettingsConfigDict(extra="ignore", populate_by_name=True)


class OpenAISettings(BaseSettings):
    api_key: str = Field(default="", alias="OPENAI_API_KEY")
    model: str = Field(default="gpt-4o", alias="OPENAI_MODEL")
    realtime_model: str = Field(
        default="gpt-4o-realtime-preview-2024-12-17", alias="OPENAI_REALTIME_MODEL"
    )
    vision_model: str = Field(default="gpt-4o", alias="OPENAI_VISION_MODEL")
    tts_voice: str = Field(default="alloy", alias="OPENAI_TTS_VOICE")

    model_config = SettingsConfigDict(extra="ignore", populate_by_name=True)


class TwilioSettings(BaseSettings):
    account_sid: str = Field(default="", alias="TWILIO_ACCOUNT_SID")
    auth_token: str = Field(default="", alias="TWILIO_AUTH_TOKEN")
    phone_number: str = Field(default="", alias="TWILIO_PHONE_NUMBER")

    model_config = SettingsConfigDict(extra="ignore", populate_by_name=True)


class EmailSettings(BaseSettings):
    smtp_host: str = Field(default="smtp.gmail.com", alias="SMTP_HOST")
    smtp_port: int = Field(default=587, alias="SMTP_PORT")
    smtp_username: str = Field(default="", alias="SMTP_USERNAME")
    smtp_password: str = Field(default="", alias="SMTP_PASSWORD")
    from_email: str = Field(
        default="noreply@diagnostic.example.com", alias="SMTP_FROM_EMAIL"
    )
    from_name: str = Field(default="Diagnostic Agent", alias="SMTP_FROM_NAME")
    use_tls: bool = Field(default=True, alias="SMTP_USE_TLS")

    model_config = SettingsConfigDict(extra="ignore", populate_by_name=True)


class UploadSettings(BaseSettings):
    directory: Path = Field(default=Path("./uploads"), alias="UPLOAD_DIR")
    link_ttl_hours: int = Field(default=24, alias="UPLOAD_LINK_TTL_HOURS")
    max_bytes: int = Field(default=10 * 1024 * 1024, alias="UPLOAD_MAX_BYTES")

    @field_validator("directory", mode="before")
    @classmethod
    def _expand(cls, v: str | Path) -> Path:
        return Path(v).expanduser().resolve() if v else Path("./uploads").resolve()

    model_config = SettingsConfigDict(extra="ignore", populate_by_name=True)


class BusinessSettings(BaseSettings):
    timezone: str = Field(default="America/Chicago", alias="BUSINESS_TIMEZONE")
    supported_appliances_raw: str = Field(
        default="washer,dryer,refrigerator,dishwasher,oven,hvac,microwave",
        alias="SUPPORTED_APPLIANCES",
    )

    @property
    def supported_appliances(self) -> List[str]:
        return [
            a.strip().lower()
            for a in self.supported_appliances_raw.split(",")
            if a.strip()
        ]

    model_config = SettingsConfigDict(extra="ignore", populate_by_name=True)


class Settings(BaseSettings):
    """Aggregated, singleton-like application settings."""

    app: AppSettings = Field(default_factory=AppSettings)
    database: DatabaseSettings = Field(default_factory=DatabaseSettings)
    openai: OpenAISettings = Field(default_factory=OpenAISettings)
    twilio: TwilioSettings = Field(default_factory=TwilioSettings)
    email: EmailSettings = Field(default_factory=EmailSettings)
    upload: UploadSettings = Field(default_factory=UploadSettings)
    business: BusinessSettings = Field(default_factory=BusinessSettings)

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the singleton Settings instance.

    Cached via `lru_cache` so all imports share the same in-memory object
    and we never re-parse the environment.
    """
    return Settings()


settings: Settings = get_settings()
