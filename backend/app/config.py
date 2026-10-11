"""Настройки приложения. Читаются из переменных окружения и файла .env в корне проекта."""
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/app/config.py -> корень проекта на два уровня выше папки backend
PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=PROJECT_ROOT / ".env", extra="ignore")

    database_url: str = "postgresql+psycopg://pcbuilder:pcbuilder@localhost:5433/pcbuilder"

    # Настройки LLM. Если провайдер "none" или ключ пустой, ИИ отключён
    llm_provider: str = "none"
    llm_api_key: str = ""
    llm_model: str = ""
    llm_base_url: str = ""


settings = Settings()
