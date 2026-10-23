"""Замены деталей: что даст доплата и где можно сэкономить.

Для каждой детали сборки перебираются другие детали той же категории.
Если замена ломает совместимость (например, процессор другого сокета),
зависимые детали подбираются заново (см. BuildSearch.repair), и в замене
показываются все изменения.

Для каждой замены считается:
- разница в цене, ₽;
- изменение оценки сборки в сценарии пользователя, %.

«Доплатить» — замены с приростом не меньше 2%, лучшие по приросту на рубль.
«Сэкономить» — замены, которые экономят деньги и снижают оценку не больше чем на 3%.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from app.domain import Build
from app.models import Category, Component
from app.recommender.builder import BuildSearch, format_rub
from app.recommender.params import Scenario

C = Category

ALTERNATIVE_CATEGORIES = [C.GPU, C.CPU, C.RAM, C.STORAGE, C.MOTHERBOARD, C.PSU, C.CASE, C.COOLER]
MIN_UPGRADE_GAIN_PCT = 2.0
MAX_SAVING_LOSS_PCT = 3.0
MIN_SAVING_RUB = 1000
# Доплата считается выгодной, если даёт хотя бы 30% от средней «оценки за рубль» сборки
# (тот же порог, что и при «докупке» улучшений в builder.py)
WORTH_IT_EFFICIENCY = 0.3
# Доплата больше 30% бюджета — это уже другая сборка, а не замена детали
MAX_UPGRADE_SHARE = 0.3
MAX_SUGGESTIONS = 4

SCENARIO_METRIC = {
    Scenario.GAMING: "в играх",
    Scenario.WORKSTATION: "в рабочих задачах",
    Scenario.OFFICE: "по общей оценке",
}


# "upgrade" — доплатить, "saving" — сэкономить
AlternativeKind = Literal["upgrade", "saving"]


@dataclass
class Alternative:
    kind: AlternativeKind
    category: Category
    old_part: Component
    new_part: Component
    extra_changes: list[tuple[Component | None, Component]]  # вынужденные замены других деталей
    build: Build  # сборка после замены
    price_delta: int
    score_delta_pct: float
    text: str
    worth_it: bool = True  # для доплат: выгодна ли она по соотношению прирост/цена

    def as_fact(self) -> dict:
        return {"text": self.text, "worth_it": self.worth_it}


def find_alternatives(search: BuildSearch, build: Build) -> tuple[list[Alternative], list[Alternative]]:
    """Возвращает (доплатить, сэкономить) для сборки."""
    request = search.request
    base_score = search.score(build)
    max_extra = request.budget * MAX_UPGRADE_SHARE
    best_upgrade: dict[Category, Alternative] = {}
    best_saving: dict[Category, Alternative] = {}

    for category in ALTERNATIVE_CATEGORIES:
        current = build.part_in_slot(category)
        if current is None or _is_pinned(search, current):
            continue
        for candidate in _candidates(search, category):
            if candidate.id == current.id:
                continue
            new_build = search.repair(build.replace_part(candidate), keep=candidate)
            if new_build is None:
                continue
            price_delta = new_build.total_price - build.total_price
            score_delta = (search.score(new_build) - base_score) / base_score * 100
            alt = _make(search, category, build, new_build, current, candidate, price_delta, score_delta)

            if 0 < price_delta <= max_extra and score_delta >= MIN_UPGRADE_GAIN_PCT:
                prev = best_upgrade.get(category)
                if prev is None or _efficiency(alt) > _efficiency(prev):
                    best_upgrade[category] = alt
            elif price_delta <= -MIN_SAVING_RUB and score_delta >= -MAX_SAVING_LOSS_PCT:
                prev = best_saving.get(category)
                if prev is None or (alt.price_delta, -alt.score_delta_pct) < (prev.price_delta, -prev.score_delta_pct):
                    best_saving[category] = alt

    upgrades = sorted(best_upgrade.values(), key=_efficiency, reverse=True)[:MAX_SUGGESTIONS]
    avg_value = base_score / build.total_price  # средняя «оценка за рубль» сборки
    for alt in upgrades:
        gain = alt.score_delta_pct / 100 * base_score
        alt.worth_it = gain / alt.price_delta >= WORTH_IT_EFFICIENCY * avg_value
    savings = sorted(best_saving.values(), key=lambda a: a.price_delta)[:MAX_SUGGESTIONS]
    return upgrades, savings


def _efficiency(alt: Alternative) -> float:
    """Процент прироста на каждые 1000 ₽ доплаты."""
    return alt.score_delta_pct / alt.price_delta * 1000


def _is_pinned(search: BuildSearch, part: Component) -> bool:
    """Закреплённые пользователем детали не заменяем."""
    return part.id in (search.request.cpu_id, search.request.gpu_id)


def _candidates(search: BuildSearch, category: Category) -> Sequence[Component]:
    # Для процессоров учитываются предпочтения пользователя (платформа, встроенная графика)
    if category == C.CPU:
        return search.cpu_options()
    return search.catalog.of(category)


def _make(
    search: BuildSearch,
    category: Category,
    old_build: Build,
    new_build: Build,
    current: Component,
    candidate: Component,
    price_delta: int,
    score_delta: float,
) -> Alternative:
    extra = []
    for cat in ALTERNATIVE_CATEGORIES:
        if cat == category:
            continue
        before, after = old_build.part_in_slot(cat), new_build.part_in_slot(cat)
        if after is not None and (before is None or before.id != after.id):
            extra.append((before, after))

    kind: AlternativeKind = "upgrade" if price_delta > 0 else "saving"
    text = f"{candidate.title} вместо {current.title}"
    if extra:
        text += " (также: " + ", ".join(after.title for _, after in extra) + ")"
    metric = SCENARIO_METRIC[search.request.scenario]
    if kind == "upgrade":
        text += f": +{format_rub(price_delta)}, производительность {metric} +{score_delta:.0f}%"
    else:
        if score_delta <= -0.5:
            loss = f"−{abs(score_delta):.0f}%"
        elif score_delta >= 0.5:
            loss = f"даже +{score_delta:.0f}%"
        else:
            loss = "без заметной потери"
        text += f": экономия {format_rub(-price_delta)}, {metric} {loss}"
    return Alternative(kind, category, current, candidate, extra, new_build, price_delta, round(score_delta, 1), text)
