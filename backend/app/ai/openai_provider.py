"""Провайдер для OpenAI и любых OpenAI-совместимых API (DeepSeek, локальные Ollama и LM Studio и т.п.).
Адрес API задаётся в LLM_BASE_URL, модель — в LLM_MODEL (обязательно)."""
import json
import re
import time
from collections.abc import Iterator

import httpx2
import openai

from app.ai.base import LLMError

# Низкая температура: модель пересказывает факты, а не сочиняет — меньше выдуманных деталей.
# (У Anthropic параметра нет: текущие модели Claude не принимают temperature.)
TEMPERATURE = 0.3

# Сколько ждать модель. Read-таймаут — это время без новых данных от сервера: для ответа
# целиком это вся генерация, для потока — ожидание очередного куска (включая первое слово,
# которое локальная модель на слабой видеокарте выдаёт через 10+ секунд)
PARSE_TIMEOUT = openai.Timeout(30.0, connect=5.0)    # пользователь ждёт, а разбор правилами мгновенный
TEXT_TIMEOUT = openai.Timeout(120.0, connect=5.0)    # объяснение целиком, без потока
STREAM_TIMEOUT = openai.Timeout(60.0, connect=5.0)   # пауза между кусками потока

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
        # Без автоматических повторов: у каждого обращения к ИИ есть мгновенный запасной вариант
        # (правила, шаблон), а повтор после таймаута заставил бы локальную модель считать всё заново
        self.client = openai.OpenAI(api_key=api_key, base_url=base_url or None, max_retries=0)
        # Индекс в JSON_FORMATS: с какого способа начинать. Запоминается, чтобы не повторять отказы API
        self._json_format = 0

    def _chat(self, system: str, prompt: str, timeout: openai.Timeout, response_format=openai.NOT_GIVEN) -> str:
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                temperature=TEMPERATURE,
                messages=[{"role": "system", "content": system}, {"role": "user", "content": prompt}],
                response_format=response_format,
                timeout=timeout,
            )
        except openai.APIStatusError as e:
            raise LLMError(f"Ошибка API ({e.status_code})") from e
        except openai.APITimeoutError as e:
            raise LLMError(f"Модель не ответила за {timeout.read:.0f} с") from e
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
        # Лимит общий на все попытки: после отказа в формате следующая попытка получает только остаток
        deadline = time.monotonic() + PARSE_TIMEOUT.read
        while True:
            kind = JSON_FORMATS[self._json_format]
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise LLMError(f"Модель не ответила за {PARSE_TIMEOUT.read:.0f} с")
            timeout = openai.Timeout(remaining, connect=min(PARSE_TIMEOUT.connect, remaining))
            try:
                return _extract_json(self._chat(system, prompt, timeout, _response_format(kind, schema)))
            except LLMError as e:
                if isinstance(e.__cause__, openai.APITimeoutError):
                    raise LLMError(f"Модель не ответила за {PARSE_TIMEOUT.read:.0f} с") from e.__cause__
                # 400 при заданном формате — API не поддерживает этот способ, пробуем следующий
                rejected = isinstance(e.__cause__, openai.BadRequestError) and kind != "none"
                if not rejected:
                    raise
                self._json_format += 1

    def generate_text(self, system: str, prompt: str) -> str:
        return self._chat(system, prompt, TEXT_TIMEOUT)

    def stream_text(self, system: str, prompt: str) -> Iterator[str]:
        got_text = False
        try:
            stream = self.client.chat.completions.create(
                model=self.model,
                temperature=TEMPERATURE,
                messages=[{"role": "system", "content": system}, {"role": "user", "content": prompt}],
                stream=True,
                timeout=STREAM_TIMEOUT,
            )
            with stream:
                for chunk in stream:
                    delta = chunk.choices[0].delta.content if chunk.choices else None
                    if delta:
                        got_text = True
                        yield delta
        except openai.APIStatusError as e:
            raise LLMError(f"Ошибка API ({e.status_code})") from e
        except (openai.APITimeoutError, httpx2.TimeoutException) as e:
            raise LLMError(f"Модель молчала дольше {STREAM_TIMEOUT.read:.0f} с") from e
        except (openai.APIError, httpx2.TransportError) as e:
            # Соединение может оборваться и посреди потока, когда часть текста уже выдана
            raise LLMError("Соединение с API прервалось") from e
        if not got_text:
            raise LLMError("Пустой ответ модели")
