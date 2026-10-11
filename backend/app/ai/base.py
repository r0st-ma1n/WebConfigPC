"""Интерфейс провайдера LLM. Чтобы подключить новый провайдер, достаточно
реализовать два метода и добавить его в factory.py."""
from typing import Protocol


class LLMError(Exception):
    """Модель недоступна или вернула неподходящий ответ. Вызывающий код
    в этом случае переходит на запасной вариант без ИИ."""


class LLMProvider(Protocol):
    name: str
    model: str

    def generate_json(self, system: str, prompt: str, schema: dict) -> dict:
        """Ответ модели в виде JSON, соответствующего schema."""
        ...

    def generate_text(self, system: str, prompt: str) -> str:
        """Обычный текстовый ответ."""
        ...
