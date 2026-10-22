"""Распределение бюджета по категориям в зависимости от сценария.

Доли — ориентир для подбора второстепенных деталей (плата, память, накопитель,
блок питания, корпус, охлаждение): алгоритм берёт лучшую деталь, которая
укладывается в свою долю. Процессор и видеокарта перебираются полностью,
поэтому их доли используются для объяснения выбора и диаграммы на фронтенде.
"""

from app.balance import Resolution
from app.models import Category
from app.recommender.params import Scenario

C = Category

BASE_SHARES: dict[Scenario, dict[Category, float]] = {
    # В играх главное — видеокарта
    Scenario.GAMING: {
        C.CPU: 0.20,
        C.GPU: 0.40,
        C.MOTHERBOARD: 0.10,
        C.RAM: 0.08,
        C.STORAGE: 0.07,
        C.PSU: 0.07,
        C.CASE: 0.05,
        C.COOLER: 0.03,
    },
    # Рендер и кодирование видео нагружают процессор и память
    Scenario.WORKSTATION: {
        C.CPU: 0.30,
        C.GPU: 0.28,
        C.MOTHERBOARD: 0.10,
        C.RAM: 0.12,
        C.STORAGE: 0.08,
        C.PSU: 0.06,
        C.CASE: 0.04,
        C.COOLER: 0.02,
    },
    # Для офиса хватает встроенной графики, важнее отзывчивость: процессор и SSD
    Scenario.OFFICE: {
        C.CPU: 0.35,
        C.GPU: 0.00,
        C.MOTHERBOARD: 0.15,
        C.RAM: 0.12,
        C.STORAGE: 0.15,
        C.PSU: 0.10,
        C.CASE: 0.10,
        C.COOLER: 0.03,
    },
}

# В играх с ростом разрешения нагрузка смещается на видеокарту:
# её доля растёт за счёт процессора (60%) и платы (40%)
GPU_SHIFT_BY_RESOLUTION = {
    Resolution.FHD: -0.04,
    Resolution.QHD: 0.0,
    Resolution.UHD: +0.06,
}


def budget_shares(scenario: Scenario, resolution: Resolution = Resolution.QHD) -> dict[Category, float]:
    shares = dict(BASE_SHARES[scenario])
    if scenario == Scenario.GAMING:
        shift = GPU_SHIFT_BY_RESOLUTION[resolution]
        shares[C.GPU] += shift
        shares[C.CPU] -= shift * 0.6
        shares[C.MOTHERBOARD] -= shift * 0.4
    return shares


def allocate_budget(budget: int, scenario: Scenario, resolution: Resolution = Resolution.QHD) -> dict[Category, int]:
    """Сколько рублей приходится на каждую категорию."""
    return {cat: round(budget * share) for cat, share in budget_shares(scenario, resolution).items()}
