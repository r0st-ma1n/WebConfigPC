"""Провайдер Anthropic (Claude) через официальный SDK."""
import json
import logging

import anthropic

from app.ai.base import LLMError

log = logging.getLogger(__name__)

DEFAULT_MODEL = "claude-opus-5-5"
# Модели, которые поддерживают серверный запасной вариант при отказе модели (fallbacks)
# и параметр effort. Для остальных моделей эти параметры не передаются.
MODERN_MODELS = {"claude-opus-5-5", "claude-opus-5", "claude-fable-5-1", "claude-sonnet-5-5"}


class AnthropicProvider:
    name = "anthropic"

    def __init__(self, api_key: str, model: str = ""):
        self.model = model or DEFAULT_MODEL
        # Короткий таймаут: пользователь ждёт ответа в интерфейсе
        self.client = anthropic.Anthropic(api_key=api_key, timeout=60.0, max_retries=1)

    def _create(self, system: str, prompt: str, output_format: dict | None = None) -> str:
        kwargs: dict = {}
        output_config: dict = {}
        if self.model in MODERN_MODELS:
            # Задачи простые: низкий уровень рассуждений — быстрее и дешевле
            output_config["effort"] = "low"
            # Если классификатор безопасности модели ошибочно отклонит запрос,
            # API само повторит его на рекомендованной запасной модели
            kwargs["betas"] = ["server-side-fallback-2026-07-01"]
            kwargs["fallbacks"] = "default"
        if output_format:
            output_config["format"] = output_format
        if output_config:
            kwargs["output_config"] = output_config
        try:
            response = self.client.beta.messages.create(
                model=self.model,
                max_tokens=16000,
                system=system,
                messages=[{"role": "user", "content": prompt}],
                **kwargs,
            )
        except anthropic.AuthenticationError as e:
            raise LLMError("Неверный ключ API Anthropic") from e
        except anthropic.RateLimitError as e:
            raise LLMError("Превышен лимит запросов к Anthropic") from e
        except anthropic.APIStatusError as e:
            raise LLMError(f"Ошибка API Anthropic ({e.status_code})") from e
        except anthropic.APIConnectionError as e:
            raise LLMError("Нет соединения с API Anthropic") from e

        if response.stop_reason == "refusal":
            raise LLMError("Модель отказалась отвечать")
        text = next((b.text for b in response.content if b.type == "text"), None)
        if not text:
            raise LLMError("Пустой ответ модели")
        return text

    def generate_json(self, system: str, prompt: str, schema: dict) -> dict:
        # Структурированный вывод: API гарантирует JSON по схеме
        text = self._create(system, prompt, {"type": "json_schema", "schema": schema})
        try:
            return json.loads(text)
        except json.JSONDecodeError as e:
            raise LLMError("Модель вернула некорректный JSON") from e

    def generate_text(self, system: str, prompt: str) -> str:
        return self._create(system, prompt)
