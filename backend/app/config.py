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

    # Вход: срок жизни сессии и флаг Secure у cookie (true, когда сайт работает по HTTPS)
    session_ttl_days: int = 30
    cookie_secure: bool = False
    # Попыток входа и регистрации в минуту с одного адреса — защита от перебора паролей
    auth_rate_limit_per_minute: int = 10

    # Redis для общих между экземплярами бэкенда счётчиков лимитов и версии каталога.
    # Пусто — всё хранится в памяти процесса (достаточно для одного экземпляра)
    redis_url: str = ""
    # Сколько секунд каталог живёт в памяти процесса без проверки. С Redis каталог
    # перечитывается сразу после импорта цен, TTL нужен на случай правки базы вручную
    catalog_cache_seconds: int = 300
    # Сколько секунд хранить в Redis готовые результаты подбора (0 — не кэшировать)
    recommend_cache_seconds: int = 3600

    log_level: str = "INFO"
    # JSON-логи для сборщиков логов; в разработке удобнее обычный текст
    log_json: bool = False

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()
