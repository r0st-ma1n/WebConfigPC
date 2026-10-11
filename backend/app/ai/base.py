"""Интерфейс провайдера LLM. Чтобы подключить новый провайдер, достаточно
реализовать три метода и добавить его в factory.py."""
from collections.abc import Iterator
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

    def stream_text(self, system: str, prompt: str) -> Iterator[str]:
        """Текстовый ответ по частям, по мере генерации. LLMError может возникнуть
        и до первой части, и посреди потока — тогда уже выданный текст недействителен."""
        ...
