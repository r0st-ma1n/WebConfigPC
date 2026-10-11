"""Сценарии использования ИИ: разбор запроса и объяснение сборки.

Каждая функция сначала пробует LLM, а при её отсутствии или ошибке
переходит на вариант без ИИ. Пользователь всегда получает результат.
"""
import json
import logging
import re

from pydantic import BaseModel, ValidationError

from app.ai.base import LLMError
from app.ai.factory import get_provider
from app.ai.rules_parser import ParsedQuery, parse_query
from app.balance import Resolution
from app.models import Category, Component
from app.recommender.builder import format_rub
from app.recommender.explain import template_explanation
from app.recommender.params import SCENARIO_TITLES, Platform, Scenario
from app.schemas import RecommendIn

log = logging.getLogger(__name__)

# ---------- Разбор запроса ----------

PARSE_SYSTEM = """Ты — модуль разбора запросов в конфигураторе ПК. Пользователь описывает, какой компьютер хочет.
Извлеки параметры подбора:
- budget — бюджет в рублях целым числом («120 тысяч», «120к» = 120000); null, если не указан;
- scenario — gaming (игры, стриминг), workstation (монтаж видео, 3D, рендер, дизайн, программирование
  тяжёлых проектов) или office (офис, учёба, интернет); null, если непонятно;
- resolution — 1080p, 1440p или 4k (только для игр; «2K» = 1440p); null, если не указано;
- platform — amd или intel, только если пользователь явно хочет процессор этой фирмы; иначе null;
- gpu_query / cpu_query — конкретная модель видеокарты / процессора, если пользователь её назвал
  (например, «RTX 5070», «Ryzen 7 7800X3D»); иначе null;
- notes — одно короткое предложение на русском: что понято и чего не хватает.
Не придумывай того, чего нет в запросе."""

PARSE_SCHEMA = {
    "type": "object",
    "properties": {
        "budget": {"anyOf": [{"type": "integer"}, {"type": "null"}]},
        "scenario": {"anyOf": [{"type": "string", "enum": [s.value for s in Scenario]}, {"type": "null"}]},
        "resolution": {"anyOf": [{"type": "string", "enum": [r.value for r in Resolution]}, {"type": "null"}]},
        "platform": {"anyOf": [{"type": "string", "enum": [p.value for p in Platform]}, {"type": "null"}]},
        "gpu_query": {"anyOf": [{"type": "string"}, {"type": "null"}]},
        "cpu_query": {"anyOf": [{"type": "string"}, {"type": "null"}]},
        "notes": {"type": "string"},
    },
    "required": ["budget", "scenario", "resolution", "platform", "gpu_query", "cpu_query", "notes"],
    "additionalProperties": False,
}


class _LLMParse(BaseModel):
    """Проверка ответа модели: если модель вернула что-то не то, ответ отбрасывается."""
    budget: int | None
    scenario: Scenario | None
    resolution: Resolution | None
    platform: Platform | None
    gpu_query: str | None
    cpu_query: str | None
    notes: str


def _normalize(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", text.lower())


def find_part(parts: list[Component], category: Category, query: str | None) -> Component | None:
    """Ищет деталь по названию («rtx 5070» -> Palit GeForce RTX 5070 Infinity 3).
    Из нескольких подходящих берётся самая дешёвая."""
    if not query:
        return None
    q = _normalize(query)
    if not q:
        return None
    matches = []
    for p in parts:
        if p.category != category:
            continue
        names = [_normalize(p.name)]
        if category == Category.GPU:
            names.append(_normalize(p.chip))
        # «rtx5070» не должен совпадать с «rtx5070ti»: для чипа требуем точное совпадение
        if any(q == n for n in names[1:]) or (category == Category.CPU and q in names[0]):
            matches.append(p)
    return min(matches, key=lambda p: p.price_rub) if matches else None


def _to_params(parsed: ParsedQuery, parts: list[Component]) -> tuple[RecommendIn | None, list[str]]:
    notes = list(parsed.notes)
    if parsed.budget is None:
        notes.append("Не удалось понять бюджет — укажите его в форме.")
        return None, notes
    scenario = parsed.scenario
    if scenario is None:
        scenario = Scenario.GAMING
        notes.append("Сценарий не указан — выбраны игры, его можно поменять в форме.")
    gpu = find_part(parts, Category.GPU, parsed.gpu_query)
    cpu = find_part(parts, Category.CPU, parsed.cpu_query)
    if parsed.gpu_query and gpu is None:
        notes.append(f"Видеокарты «{parsed.gpu_query}» нет в каталоге — подберу сам.")
    if parsed.cpu_query and cpu is None:
        notes.append(f"Процессора «{parsed.cpu_query}» нет в каталоге — подберу сам.")
    params = RecommendIn(
        budget=parsed.budget,
        scenario=scenario,
        resolution=parsed.resolution or Resolution.QHD,
        platform=None if cpu else parsed.platform,
        cpu_id=cpu.id if cpu else None,
        gpu_id=gpu.id if gpu else None,
    )
    return params, notes


def _summary(params: RecommendIn, parts: list[Component]) -> str:
    by_id = {p.id: p for p in parts}
    text = f"Понял так: {SCENARIO_TITLES[params.scenario]}, бюджет {format_rub(params.budget)}"
    if params.scenario == Scenario.GAMING:
        text += f", разрешение {params.resolution.value}"
    if params.platform:
        text += f", платформа {params.platform.value.upper()}"
    if params.gpu_id:
        text += f", видеокарта {by_id[params.gpu_id].title}"
    if params.cpu_id:
        text += f", процессор {by_id[params.cpu_id].title}"
    return text + "."


def parse_request(text: str, parts: list[Component]) -> tuple[RecommendIn | None, str, str]:
    """Свободный текст -> (параметры подбора, источник "llm"/"rules", пояснение)."""
    provider = get_provider()
    parsed: ParsedQuery | None = None
    source = "rules"
    if provider is not None:
        try:
            raw = _LLMParse.model_validate(provider.generate_json(PARSE_SYSTEM, text, PARSE_SCHEMA))
            parsed = ParsedQuery(**raw.model_dump(exclude={"notes"}), notes=[])
            source = "llm"
        except (LLMError, ValidationError) as e:
            log.warning("LLM не разобрала запрос, используются правила: %s", e)
    if parsed is None:
        parsed = parse_query(text)

    params, notes = _to_params(parsed, parts)
    if params is not None:
        notes.insert(0, _summary(params, parts))
    return params, source, " ".join(notes)


# ---------- Объяснение сборки ----------

EXPLAIN_SYSTEM = """Ты — консультант магазина компьютеров. Объясни человеку, который не разбирается в железе,
почему ему предложена эта сборка ПК. Сборку подобрал алгоритм, все данные о ней даны в JSON.

Правила:
- Используй только факты из JSON. Не придумывай характеристики, цены, тесты FPS и другие детали.
- Не предлагай другие комплектующие, кроме тех, что указаны в upgrades и savings.
- Пиши по-русски, просто и дружелюбно, без жаргона (если нужен термин — поясни его).
- 3–5 коротких абзацев обычным текстом, без заголовков, списков и markdown.
- Начни с главного: для чего эта сборка и на чём сделан акцент.
- Если есть warnings, честно и спокойно упомяни их.
- В конце коротко: что даст доплата (первый пункт upgrades) и где можно сэкономить (первый пункт savings), если они есть."""


def explain(facts: dict) -> tuple[str, str]:
    """Объяснение сборки -> (текст, источник "llm"/"template")."""
    provider = get_provider()
    if provider is not None:
        try:
            prompt = "Данные о сборке:\n" + json.dumps(facts, ensure_ascii=False, indent=1)
            return provider.generate_text(EXPLAIN_SYSTEM, prompt).strip(), "llm"
        except LLMError as e:
            log.warning("LLM не сформировала объяснение, используется шаблон: %s", e)
    return template_explanation(facts), "template"
