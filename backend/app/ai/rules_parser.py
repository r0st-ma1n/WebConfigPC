"""Разбор свободного запроса без LLM — по ключевым словам и регулярным выражениям.

Понимает типовые формулировки: «игровой ПК в 1440p до 120 тысяч», «для монтажа
за 150к на интеле», «компьютер для учёбы 40000 руб». Используется, когда LLM
не подключена или вернула ошибку.
"""
import re
from dataclasses import dataclass, field

from app.balance import Resolution
from app.recommender.params import Platform, Scenario

# Число + множитель: «120 тысяч», «120к», «1,5 млн», «95 000 руб»
_MONEY = re.compile(
    r"(\d+(?:[.,]\d+)?)\s*(млн|миллион\w*|тыс\w*|т\.?\s?р\.?|k|к)?(?![\w])",
    re.IGNORECASE,
)

SCENARIO_KEYWORDS = {
    Scenario.WORKSTATION: ["монтаж", "видео", "3d", "3д", "рендер", "blender", "davinci", "premiere",
                           "after effects", "моделир", "дизайн", "cad", "автокад", "для работы"],
    Scenario.OFFICE: ["офис", "учеб", "учёб", "документ", "браузер", "word", "excel", "школ",
                      "интернет", "бухгалт"],
    Scenario.GAMING: ["игр", "гейм", "gaming", "fps", "кс", "cs2", "dota", "дота", "киберспорт",
                      "стрим", "ааа", "aaa"],
}

RESOLUTION_PATTERNS = [
    (Resolution.UHD, r"4\s?k|2160|uhd|4к"),
    (Resolution.QHD, r"1440|2\s?k|qhd|2к"),
    (Resolution.FHD, r"1080|full\s?hd|fhd|фулл"),
]

PLATFORM_PATTERNS = [
    (Platform.AMD, r"\bamd\b|ryzen|райзен|амд"),
    (Platform.INTEL, r"intel|интел|\bcore\s?(i\d|ultra)"),
]

GPU_PATTERN = re.compile(r"\b(rtx|gtx|rx|arc)\s*-?\s*([a-z]?\d{3,4})\s*(ti|xtx|xt|super)?\b", re.IGNORECASE)
CPU_PATTERN = re.compile(
    r"\b(ryzen\s*\d\s*\d{4}\w*|i[3579]\s*-?\s*\d{4,5}\w*|ultra\s*\d\s*\d{3}k?)\b", re.IGNORECASE,
)


@dataclass
class ParsedQuery:
    budget: int | None = None
    scenario: Scenario | None = None
    resolution: Resolution | None = None
    platform: Platform | None = None
    gpu_query: str | None = None
    cpu_query: str | None = None
    notes: list[str] = field(default_factory=list)


def parse_budget(text: str) -> int | None:
    """Самое правдоподобное число-бюджет в тексте (не меньше 10 000 ₽)."""
    candidates = []
    # Убираем пробелы-разделители разрядов: «120 000» -> «120000»
    compact = re.sub(r"(?<=\d)[\s ](?=\d{3}\b)", "", text)
    for number, unit in _MONEY.findall(compact.lower()):
        value = float(number.replace(",", "."))
        if unit.startswith(("млн", "миллион")):
            value *= 1_000_000
        elif unit:
            value *= 1_000
        if 10_000 <= value <= 5_000_000:
            candidates.append(int(value))
    return max(candidates) if candidates else None


def parse_query(text: str) -> ParsedQuery:
    lower = text.lower()
    result = ParsedQuery(budget=parse_budget(text))

    for resolution, pattern in RESOLUTION_PATTERNS:
        if re.search(pattern, lower):
            result.resolution = resolution
            break

    # Сценарий: побеждает тот, чьих ключевых слов больше.
    # Слово «видеокарта» убираем, иначе «видео» в нём засчитается как монтаж
    words_text = re.sub(r"видеокарт\w*", "", lower)
    hits = {s: sum(word in words_text for word in words) for s, words in SCENARIO_KEYWORDS.items()}
    top = max(hits.values())
    leaders = [s for s, n in hits.items() if n == top and n > 0]
    if result.resolution and (not leaders or Scenario.GAMING in leaders):
        result.scenario = Scenario.GAMING  # разрешение упоминают обычно про игры
    elif leaders:
        result.scenario = leaders[0]

    if m := GPU_PATTERN.search(text):
        result.gpu_query = " ".join(part for part in m.groups() if part)
    if m := CPU_PATTERN.search(text):
        result.cpu_query = m.group(1)

    for platform, pattern in PLATFORM_PATTERNS:
        if re.search(pattern, lower):
            result.platform = platform
            break
    return result
