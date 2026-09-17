"""Application configuration loaded from environment variables."""

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Jira Emulator configuration."""

    DATABASE_URL: str = "sqlite+aiosqlite:///data/jira.db"
    HOST: str = "0.0.0.0"
    PORT: int = 8080
    AUTH_MODE: Literal["permissive", "strict", "none"] = "permissive"
    IMPORT_ON_STARTUP: bool = False
    IMPORT_DIR: str = "/data/import"
    BASE_URL: str = "http://localhost:8080"
    DEFAULT_USER: str = "admin"
    LOG_LEVEL: str = "INFO"
    SEED_DATA: bool = True
    ADMIN_PASSWORD: str = "admin"
    ATTACHMENT_DIR: str = "/data/attachments"
    DESCRIPTION_MAX_LENGTH: int = Field(
        default=32767,
        ge=0,
        description="Maximum logical description characters after ADF normalization.",
    )
    WEBHOOKS_ENABLED: bool = True
    WEBHOOK_ALLOW_INSECURE_HTTP: bool = False
    WEBHOOK_ALLOW_PRIVATE_NETWORKS: bool = False
    WEBHOOK_WORKER_POLL_SECONDS: float = 1.0
    WEBHOOK_MAX_CONCURRENCY: int = 20
    WEBHOOK_CONNECT_TIMEOUT_SECONDS: float = 10.0
    WEBHOOK_TOTAL_TIMEOUT_SECONDS: float = 30.0
    WEBHOOK_SECRET_KEY: str | None = None

    model_config = {"env_prefix": "", "case_sensitive": True}


@lru_cache
def get_settings() -> Settings:
    return Settings()
