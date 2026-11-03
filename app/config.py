"""Configuração validada, carregada a cada inicialização da aplicação."""

from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from pydantic import AliasChoices, Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Variáveis EMPORIO_* têm precedência sobre o arquivo .env local."""

    model_config = SettingsConfigDict(
        env_prefix="EMPORIO_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        env_ignore_empty=True,
        populate_by_name=True,
        hide_input_in_errors=True,
    )

    environment: Literal["development", "test", "production"] = "development"
    llm_provider: Literal["openai", "openai_compatible"] | None = None
    llm_model: str | None = Field(default=None, min_length=1, max_length=160)
    llm_api_key: SecretStr | None = Field(
        default=None,
        repr=False,
        validation_alias=AliasChoices("EMPORIO_LLM_API_KEY", "OPENAI_API_KEY"),
    )
    llm_base_url: str | None = Field(default=None, repr=False)
    llm_structured_finalization: bool = False
    llm_temperature: float | None = Field(default=None, ge=0, le=2)
    llm_reasoning_effort: Literal["none", "low", "medium", "high"] | None = None
    llm_timeout_seconds: float = Field(default=20, gt=0, le=60)
    llm_max_output_tokens: int = Field(default=1200, ge=128, le=4096)
    agent_timeout_seconds: float = Field(default=30, gt=0, le=120)
    agent_tool_timeout_seconds: float = Field(default=5, gt=0, le=30)
    agent_max_rounds: int = Field(default=4, ge=1, le=8)
    agent_max_tool_calls: int = Field(default=12, ge=1, le=32)
    session_max_turns: int = Field(default=6, ge=1, le=20)
    session_max_characters: int = Field(default=12000, ge=1000, le=60000)
    session_ttl_seconds: float = Field(default=1800, gt=0, le=86400)
    session_max_sessions: int = Field(default=100, ge=1, le=1000)
    session_max_clients: int = Field(default=100, ge=1, le=1000)
    session_lock_timeout_seconds: float = Field(default=30, gt=0, le=60)
    chat_mode: Literal["real", "offline_demo"] = "real"
    chat_catalog_database: Path = Path("data/emporio.sqlite3")
    chat_demo_database: Path = Path("data/demo.sqlite3")
    chat_policy_pdf: Path | None = None

    @field_validator("llm_model")
    @classmethod
    def nonblank_model(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("blank_llm_model")
        return value.strip() if value is not None else None

    @field_validator("llm_base_url")
    @classmethod
    def validate_base_url(cls, value: str | None) -> str | None:
        if value is None:
            return None
        parts = urlsplit(value)
        if parts.scheme not in ("http", "https") or not parts.hostname:
            raise ValueError("invalid_llm_base_url")
        if parts.username or parts.password or parts.query or parts.fragment:
            raise ValueError("credentials_or_query_in_url_not_allowed")
        return value

    @property
    def llm_configured(self) -> bool:
        return bool(
            self.llm_provider
            and self.llm_model
            and self.llm_api_key
            and self.llm_api_key.get_secret_value().strip()
            and (self.llm_provider == "openai" or self.llm_base_url)
        )
