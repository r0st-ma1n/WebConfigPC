"""Провайдер для OpenAI и любых OpenAI-совместимых API (DeepSeek, локальные Ollama и LM Studio и т.п.).
Адрес API задаётся в LLM_BASE_URL, модель — в LLM_MODEL (обязательно)."""
import json
import re

import openai

from app.ai.base import LLMError

# Способы запросить JSON, от самого простого к самому совместимому. Разные API поддерживают разное:
# OpenAI и Ollama принимают json_object, LM Studio — только json_schema, а кто-то не знает ни того, ни другого
JSON_FORMATS = ("json_object", "json_schema", "none")

_THINK = re.compile(r"<think>.*?</think>", re.DOTALL)
_FENCE = re.compile(r"^```(?:json)?\s*(.*?)\s*```$", re.DOTALL)


def _response_format(kind: str, schema: dict):
    if kind == "json_object":
        return {"type": "json_object"}
    if kind == "json_schema":
        return {"type": "json_schema", "json_schema": {"name": "answer", "schema": schema}}
    return openai.NOT_GIVEN


def _extract_json(text: str) -> dict:
    """JSON из ответа модели: без блока размышлений <think> и без обёртки ```json."""
    text = _THINK.sub("", text).strip()
    if m := _FENCE.match(text):
        text = m.group(1)
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        raise LLMError("Модель вернула некорректный JSON") from e


class OpenAICompatibleProvider:
    name = "openai"

    def __init__(self, api_key: str, model: str, base_url: str = ""):
        if not model:
            raise ValueError("Для провайдера openai нужно указать LLM_MODEL")
        self.model = model
        self.client = openai.OpenAI(api_key=api_key, base_url=base_url or None, timeout=60.0, max_retries=1)
        # Индекс в JSON_FORMATS: с какого способа начинать. Запоминается, чтобы не повторять отказы API
        self._json_format = 0

    def _chat(self, system: str, prompt: str, response_format=openai.NOT_GIVEN) -> str:
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "system", "content": system}, {"role": "user", "content": prompt}],
                response_format=response_format,
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
        # Схема дублируется в инструкции: при формате "none" модель узнает о ней только так,
        # а ответ в любом случае проверяется Pydantic-моделью в service.py
        system = f"{system}\n\nОтветь только JSON по этой JSON-схеме:\n{json.dumps(schema, ensure_ascii=False)}"
        while True:
            kind = JSON_FORMATS[self._json_format]
            try:
                return _extract_json(self._chat(system, prompt, _response_format(kind, schema)))
            except LLMError as e:
                # 400 при заданном формате — API не поддерживает этот способ, пробуем следующий
                rejected = isinstance(e.__cause__, openai.BadRequestError) and kind != "none"
                if not rejected:
                    raise
                self._json_format += 1

    def generate_text(self, system: str, prompt: str) -> str:
        return self._chat(system, prompt)
