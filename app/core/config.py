"""Application configuration via Pydantic Settings.

Uses environment variables loaded from a ``.env`` file.

Google-style docstrings are used across the codebase.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any, Literal, Optional

from pydantic import AnyUrl, BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class _RedisDsn(AnyUrl):
    allowed_schemes = {"redis", "rediss"}
    host_required = True


class _PostgresDsn(AnyUrl):
    allowed_schemes = {"postgresql+asyncpg"}
    host_required = True


class Settings(BaseSettings):
    """App settings loaded from environment.

    Attributes:
        app_name: Human readable application name.
        env: Deployment environment slug.
        api_host: Host for FastAPI server.
        api_port: Port for FastAPI server.
        bot_token: Telegram bot token for Aiogram.
        database_url: Async SQLAlchemy DSN for Postgres (asyncpg).
        redis_url: Redis connection URL.
        sentry_dsn: Optional Sentry DSN for error reporting.
        openai_api_key: Optional key for OpenAI-compatible SDK.
        log_level: Log level string (e.g., "INFO").
    """

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = Field(default="Куда пойти: Крым/Севастополь")
    env: Literal["dev", "test", "prod"] = Field(default="dev")

    api_host: str = Field(default="0.0.0.0")
    api_port: int = Field(default=8000)

    bot_token: str = Field(default="", repr=False)

    database_url: _PostgresDsn = Field(
        default="postgresql+asyncpg://postgres:postgres@localhost:5432/cudacrimea"
    )
    redis_url: _RedisDsn = Field(default="redis://localhost:6379/0")

    sentry_dsn: Optional[str] = Field(default=None, repr=False)
    openai_api_key: Optional[str] = Field(default=None, repr=False)
    openai_base_url: Optional[str] = Field(default=None, alias="OPENAI_BASE_URL")
    openai_model_extractor: str = Field(default="gpt-4o-mini", alias="OPENAI_MODEL_EXTRACTOR")
    openai_model_classifier: str = Field(default="gpt-4o-mini", alias="OPENAI_MODEL_CLASSIFIER")
    openai_model_summarizer: str = Field(default="gpt-4o-mini", alias="OPENAI_MODEL_SUMMARIZER")

    # AI Mediator (OpenAI-compatible) overrides
    ai_mediator_base_url: Optional[str] = Field(default=None, alias="AI_MEDIATOR_BASE_URL")
    ai_mediator_api_key: Optional[str] = Field(default=None, alias="AI_MEDIATOR_API_KEY")
    llm_auth_header: str = Field(default="Authorization", alias="LLM_AUTH_HEADER")
    llm_auth_scheme: str = Field(default="Bearer", alias="LLM_AUTH_SCHEME")

    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = Field(
        default="INFO"
    )

    # Ranking weights
    w_time: float = Field(default=0.3, alias="W_TIME")
    w_geo: float = Field(default=0.3, alias="W_GEO")
    w_interest: float = Field(default=0.2, alias="W_INTEREST")
    w_source: float = Field(default=0.1, alias="W_SOURCE")
    w_pop: float = Field(default=0.1, alias="W_POP")
    # Optional weight for "is_open" in place ranking
    w_open: float = Field(default=0.0, alias="W_OPEN")

    # Telegram ingestion
    tg_api_id: Optional[int] = Field(default=None, alias="TELEGRAM_API_ID")
    tg_api_hash: Optional[str] = Field(default=None, alias="TELEGRAM_API_HASH")
    tg_session: Optional[str] = Field(default=None, alias="TELEGRAM_SESSION")
    tg_channels_list: list[str] = Field(default_factory=list)
    tg_channels_env: Optional[str] = Field(default=None, alias="TG_CHANNELS", repr=False)

    def model_post_init(self, __context: Any) -> None:  # type: ignore[override]
        # Support comma-separated TG_CHANNELS from env
        if isinstance(self.tg_channels_env, str) and self.tg_channels_env:
            self.tg_channels_list = [
                c.strip() for c in self.tg_channels_env.split(",") if c.strip()
            ]

    @property
    def tg_channels(self) -> list[str]:
        return list(self.tg_channels_list)

    @property
    def api_base_url(self) -> str:
        """Construct API base URL for internal service communication.

        Returns:
            str: Full API base URL (e.g., http://api:8000 in Docker).
        """
        return f"http://{self.api_host}:{self.api_port}"

    # Places provider API keys
    two_gis_api_key: Optional[str] = Field(default=None, alias="TWO_GIS_API_KEY")
    yandex_maps_api_key: Optional[str] = Field(default=None, alias="YANDEX_MAPS_API_KEY")
    yandex_maps_search_url: str = Field(default="https://search-maps.yandex.ru/v1/")

    # Admin panel
    admin_user: Optional[str] = Field(default=None, alias="ADMIN_USER")
    admin_password: Optional[str] = Field(default=None, alias="ADMIN_PASSWORD")
    admin_token: Optional[str] = Field(default=None, alias="ADMIN_TOKEN")
    admin_secret: str = Field(default="change-me", alias="ADMIN_SECRET")


class Runtime(BaseModel):
    """Computed runtime flags and metadata."""

    is_docker: bool = Field(default=False)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return singleton settings instance.

    Returns:
        Settings: Loaded settings instance.
    """

    return Settings()  # type: ignore[call-arg]
