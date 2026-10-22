"""Выбор провайдера LLM по настройкам из .env."""

import logging
from functools import cache

from app.ai.base import LLMProvider
from app.config import settings

log = logging.getLogger(__name__)


@cache
def get_provider() -> LLMProvider | None:
    """Провайдер или None, если ИИ отключён (LLM_PROVIDER=none или нет ключа)."""
    kind = settings.llm_provider.strip().lower()
    key = settings.llm_api_key.strip()
    if kind in ("", "none") or not key:
        return None
    try:
        if kind == "anthropic":
            from app.ai.anthropic_provider import AnthropicProvider

            return AnthropicProvider(key, settings.llm_model)
        if kind == "openai":
            from app.ai.openai_provider import OpenAICompatibleProvider

            return OpenAICompatibleProvider(key, settings.llm_model, settings.llm_base_url)
    except ValueError as e:
        log.warning("ИИ отключён: %s", e)
        return None
    log.warning("Неизвестный LLM_PROVIDER=%r, ИИ отключён", kind)
    return None
