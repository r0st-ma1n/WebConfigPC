"""Провайдер Anthropic (Claude) через официальный SDK."""

import json
import logging
from collections.abc import Iterator
from contextlib import contextmanager

import anthropic

from app.ai.base import LLMError

log = logging.getLogger(__name__)

DEFAULT_MODEL = "claude-opus-5-5"
# Модели, которые поддерживают серверный запасной вариант при отказе модели (fallbacks)
# и параметр effort. Для остальных моделей эти параметры не передаются.
MODERN_MODELS = {"claude-opus-5-5", "claude-opus-5", "claude-fable-5-1", "claude-sonnet-5-5"}


@contextmanager
def _api_errors():
    """Ошибки SDK -> LLMError, чтобы вызывающий код перешёл на запасной вариант."""
    try:
        yield
    except anthropic.AuthenticationError as e:
        raise LLMError("Неверный ключ API Anthropic") from e
    except anthropic.RateLimitError as e:
        raise LLMError("Превышен лимит запросов к Anthropic") from e
    except anthropic.APIStatusError as e:
        raise LLMError(f"Ошибка API Anthropic ({e.status_code})") from e
    except anthropic.APIConnectionError as e:
        raise LLMError("Нет соединения с API Anthropic") from e


class AnthropicProvider:
    name = "anthropic"

    def __init__(self, api_key: str, model: str = ""):
        self.model = model or DEFAULT_MODEL
        # Короткий таймаут: пользователь ждёт ответа в интерфейсе
        self.client = anthropic.Anthropic(api_key=api_key, timeout=60.0, max_retries=1)

    def _params(self, system: str, prompt: str, output_format: dict | None = None) -> dict:
        params: dict = {
            "model": self.model,
            "max_tokens": 16000,
            "system": system,
            "messages": [{"role": "user", "content": prompt}],
        }
        output_config: dict = {}
        if self.model in MODERN_MODELS:
            # Задачи простые: низкий уровень рассуждений — быстрее и дешевле
            output_config["effort"] = "low"
            # Если классификатор безопасности модели ошибочно отклонит запрос,
            # API само повторит его на рекомендованной запасной модели
            params["betas"] = ["server-side-fallback-2026-07-01"]
            params["fallbacks"] = "default"
        if output_format:
            output_config["format"] = output_format
        if output_config:
            params["output_config"] = output_config
        return params

    def _create(self, system: str, prompt: str, output_format: dict | None = None) -> str:
        with _api_errors():
            response = self.client.beta.messages.create(**self._params(system, prompt, output_format))
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

    def stream_text(self, system: str, prompt: str) -> Iterator[str]:
        got_text = False
        with _api_errors(), self.client.beta.messages.stream(**self._params(system, prompt)) as stream:
            for text in stream.text_stream:
                got_text = True
                yield text
            final = stream.get_final_message()
        # Отказ может прийти и после части текста — тогда выданный текст нужно отбросить
        if final.stop_reason == "refusal":
            raise LLMError("Модель отказалась отвечать")
        if not got_text:
            raise LLMError("Пустой ответ модели")
