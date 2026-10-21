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
    # Сколько запросов к LLM в минуту разрешено одному клиенту (0 — без ограничения)
    ai_rate_limit_per_minute: int = 20

    # Адреса фронтенда, которым разрешены запросы к API из браузера, через запятую.
    # В Docker фронтенд и API на одном адресе (nginx), поэтому там CORS не нужен
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    log_level: str = "INFO"
    # JSON-логи для сборщиков логов; в разработке удобнее обычный текст
    log_json: bool = False

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()
