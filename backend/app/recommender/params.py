"""Параметры подбора: что пользователь хочет получить."""
from dataclasses import dataclass
from enum import StrEnum

from app.balance import Resolution


class Scenario(StrEnum):
    GAMING = "gaming"
    WORKSTATION = "workstation"  # работа с видео и 3D
    OFFICE = "office"  # офис и учёба


SCENARIO_TITLES = {
    Scenario.GAMING: "игры",
    Scenario.WORKSTATION: "работа с видео и 3D",
    Scenario.OFFICE: "офис и учёба",
}


class Platform(StrEnum):
    AMD = "amd"
    INTEL = "intel"


class Tier(StrEnum):
    """Три варианта сборки, которые предлагает система."""

    CHEAPER = "cheaper"
    OPTIMAL = "optimal"
    HEADROOM = "headroom"


TIER_TITLES = {
    Tier.CHEAPER: "Дешевле",
    Tier.OPTIMAL: "Оптимальная",
    Tier.HEADROOM: "С запасом",
}

# Предел цены для каждого варианта как доля бюджета пользователя
TIER_BUDGET_FACTOR = {
    Tier.CHEAPER: 0.80,
    Tier.OPTIMAL: 1.00,
    Tier.HEADROOM: 1.15,
}

# Минимальные требования сценария: сборки ниже этого уровня не рассматриваются.
# Требования растут с бюджетом: для игрового ПК за 50 тыс. 16 ГБ памяти — нормально,
# а за 150 тыс. экономить на памяти уже неразумно.
# Формат: список (бюджет от, требование), берётся последняя подходящая строка.
MIN_RAM_GB = {
    Scenario.GAMING: [(0, 16), (90_000, 32)],
    Scenario.WORKSTATION: [(0, 32), (200_000, 64)],
    Scenario.OFFICE: [(0, 8), (35_000, 16)],
}
MIN_STORAGE_GB = {
    Scenario.GAMING: [(0, 480), (70_000, 1000)],
    Scenario.WORKSTATION: [(0, 1000)],
    Scenario.OFFICE: [(0, 480)],
}
# Минимальный объём видеопамяти: 4 ГБ не хватает ни современным играм, ни 3D
MIN_VRAM_GB = 8


def _threshold(table: list[tuple[int, int]], budget: int) -> int:
    return [value for start, value in table if budget >= start][-1]


@dataclass
class RecommendRequest:
    budget: int
    scenario: Scenario
    resolution: Resolution = Resolution.QHD  # учитывается только для игр
    platform: Platform | None = None
    cpu_id: int | None = None  # закреплённый пользователем процессор
    gpu_id: int | None = None  # закреплённая видеокарта

    @property
    def is_gaming(self) -> bool:
        return self.scenario == Scenario.GAMING

    @property
    def min_ram_gb(self) -> int:
        return _threshold(MIN_RAM_GB[self.scenario], self.budget)

    @property
    def min_storage_gb(self) -> int:
        return _threshold(MIN_STORAGE_GB[self.scenario], self.budget)


class RecommendError(Exception):
    """Подобрать сборку невозможно (например, слишком маленький бюджет).
    Текст исключения показывается пользователю."""
