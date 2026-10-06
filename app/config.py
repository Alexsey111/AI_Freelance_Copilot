"""Конфигурация приложения.

Все значения читаются из переменных окружения / файла .env (см. .env.example).
Секреты (API-ключи) в репозиторий не попадают никогда.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
PROMPTS_DIR = BASE_DIR / "prompts"

DEFAULT_DATABASE_URL = f"sqlite:///{(DATA_DIR / 'app.db').as_posix()}"


class Settings(BaseSettings):
    """Настройки приложения (единственный источник конфигурации)."""

    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- Application ---
    app_env: str = "development"
    app_name: str = "AI Freelance Copilot"
    log_level: str = "INFO"

    # --- Storage ---
    database_url: str = DEFAULT_DATABASE_URL
    db_echo: bool = False

    # --- LLM ---
    llm_provider: str = "mock"  # mock | openai
    llm_model: str = "gpt-4o-mini"
    llm_api_key: str | None = None
    llm_base_url: str | None = None
    llm_timeout_s: float = 60.0
    llm_temperature: float = 0.0
    llm_max_output_tokens: int = 1500

    # --- Бизнес-правила ручной проверки (ТЗ §13, §14, §29) ---
    default_profile_id: int = 1
    min_description_chars: int = 40
    match_score_review_threshold: float = 0.35
    llm_score_crosscheck_delta: float = 0.5
    min_draft_reply_chars: int = 80

    # --- Frontend ---
    backend_url: str = "http://localhost:8000"

    @property
    def is_test(self) -> bool:
        return self.app_env.lower() in {"test", "testing"}


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Кэшированный доступ к настройкам (переопределяется в тестах)."""
    return Settings()
