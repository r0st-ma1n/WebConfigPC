"""Провайдер для OpenAI и любых OpenAI-совместимых API (DeepSeek, локальная Ollama и т.п.).
Адрес API задаётся в LLM_BASE_URL, модель — в LLM_MODEL (обязательно)."""
import json

import openai

from app.ai.base import LLMError


class OpenAICompatibleProvider:
    name = "openai"

    def __init__(self, api_key: str, model: str, base_url: str = ""):
        if not model:
            raise ValueError("Для провайдера openai нужно указать LLM_MODEL")
        self.model = model
        self.client = openai.OpenAI(api_key=api_key, base_url=base_url or None, timeout=60.0, max_retries=1)

    def _chat(self, system: str, prompt: str, json_mode: bool) -> str:
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "system", "content": system}, {"role": "user", "content": prompt}],
                response_format={"type": "json_object"} if json_mode else openai.NOT_GIVEN,
            )
        except openai.APIStatusError as e:
            raise LLMError(f"Ошибка API ({e.status_code})") from e
        except openai.APIConnectionError as e:
            raise LLMError("Нет соединения с API") from e
        text = response.choices[0].message.content
        if not text:
            raise LLMError("Пустой ответ модели")
        return text

    def generate_json(self, system: str, prompt: str, schema: dict) -> dict:
        # Не все совместимые API поддерживают JSON-схемы, поэтому схема передаётся в инструкции,
        # а ответ потом проверяется Pydantic-моделью в service.py
        system = f"{system}\n\nОтветь только JSON по этой JSON-схеме:\n{json.dumps(schema, ensure_ascii=False)}"
        try:
            return json.loads(self._chat(system, prompt, json_mode=True))
        except json.JSONDecodeError as e:
            raise LLMError("Модель вернула некорректный JSON") from e

    def generate_text(self, system: str, prompt: str) -> str:
        return self._chat(system, prompt, json_mode=False)
