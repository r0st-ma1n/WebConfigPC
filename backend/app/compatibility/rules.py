"""Правила совместимости.

Каждое правило — функция (сборка) -> список нарушений. Правило проверяет только
те детали, которые уже выбраны: если, например, нет корпуса, проверки
с корпусом просто пропускаются. Поэтому правила работают и для неполной
сборки в ручном режиме.

Чтобы добавить правило, достаточно написать функцию и добавить её в RULES.
"""

import math
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum

from app.balance import BalanceKind, Resolution, check_balance
from app.domain import Build
from app.models import Component


class Level(StrEnum):
    ERROR = "error"  # собрать нельзя
    WARNING = "warning"  # собрать можно, но есть риск или неоптимальность


@dataclass
class Issue:
    level: Level
    code: str  # машинный код, по нему фронтенд и тесты узнают тип проблемы
    message: str  # текст для пользователя
    # id деталей, к которым относится нарушение. По ним ручной режим понимает,
    # какую деталь нельзя выбрать
    part_ids: list[int] = field(default_factory=list)


def _ids(*parts: Component) -> list[int]:
    return [p.id for p in parts]


# Рекомендуемый запас мощности блока питания над расчётным потреблением
PSU_HEADROOM = 1.3


def recommended_psu_w(build: Build) -> int:
    """Рекомендуемая мощность БП: потребление с запасом 30%, округлённое вверх до 50 Вт,
    но не меньше, чем советует производитель видеокарты."""
    by_power = math.ceil(build.estimated_power_w * PSU_HEADROOM / 50) * 50
    by_gpu = build.gpu.recommended_psu_w if build.gpu else 0
    return max(by_power, by_gpu)


# ---------- Процессор, плата, охлаждение ----------


def cpu_motherboard_socket(b: Build) -> list[Issue]:
    if b.cpu and b.motherboard and b.cpu.socket != b.motherboard.socket:
        return [
            Issue(
                Level.ERROR,
                "socket_mismatch",
                f"Процессор {b.cpu.title} (сокет {b.cpu.socket}) не подходит "
                f"к плате {b.motherboard.title} (сокет {b.motherboard.socket}).",
                _ids(b.cpu, b.motherboard),
            )
        ]
    return []


def cooler_socket(b: Build) -> list[Issue]:
    # Сокет кулера сверяем с сокетом процессора, а если его нет — с сокетом платы
    socket_owner = b.cpu or b.motherboard
    if b.cooler and socket_owner and socket_owner.socket not in b.cooler.sockets:
        return [
            Issue(
                Level.ERROR,
                "cooler_socket",
                f"Кулер {b.cooler.title} не поддерживает сокет {socket_owner.socket} "
                f"(поддерживает: {', '.join(b.cooler.sockets)}).",
                _ids(b.cooler, socket_owner),
            )
        ]
    return []


def cooler_tdp(b: Build) -> list[Issue]:
    if b.cooler and b.cpu and b.cooler.max_tdp_w < b.cpu.power_w:
        return [
            Issue(
                Level.WARNING,
                "cooler_weak",
                f"Кулер {b.cooler.title} рассчитан на {b.cooler.max_tdp_w} Вт, а процессор "
                f"{b.cpu.title} выделяет до {b.cpu.power_w} Вт: возможен перегрев и снижение частот.",
                _ids(b.cooler, b.cpu),
            )
        ]
    return []


# Чипсеты начального уровня: на таких платах простая подсистема питания процессора (VRM)
ENTRY_CHIPSETS = {"A520", "A620", "H610"}
# Начиная с этого потребления процессору нужна плата среднего уровня
HIGH_POWER_CPU_W = 150


def board_vrm(b: Build) -> list[Issue]:
    if b.cpu and b.motherboard and b.motherboard.chipset in ENTRY_CHIPSETS and b.cpu.power_w >= HIGH_POWER_CPU_W:
        return [
            Issue(
                Level.WARNING,
                "board_vrm",
                f"Плата {b.motherboard.title} на чипсете {b.motherboard.chipset} — начального уровня. "
                f"Её питание может не выдержать процессор {b.cpu.title} ({b.cpu.power_w} Вт) "
                f"под долгой нагрузкой: возможны перегрев платы и снижение частот.",
                _ids(b.motherboard, b.cpu),
            )
        ]
    return []


# ---------- Оперативная память ----------


def ram_type(b: Build) -> list[Issue]:
    issues = []
    if b.ram and b.motherboard and b.ram.memory_type != b.motherboard.memory_type:
        issues.append(
            Issue(
                Level.ERROR,
                "ram_type_board",
                f"Память {b.ram.title} ({b.ram.memory_type}) не подходит к плате "
                f"{b.motherboard.title}, она поддерживает только {b.motherboard.memory_type}.",
                _ids(b.ram, b.motherboard),
            )
        )
    if b.ram and b.cpu and b.ram.memory_type not in b.cpu.memory_types:
        issues.append(
            Issue(
                Level.ERROR,
                "ram_type_cpu",
                f"Процессор {b.cpu.title} не работает с памятью {b.ram.memory_type} "
                f"(поддерживает: {', '.join(b.cpu.memory_types)}).",
                _ids(b.ram, b.cpu),
            )
        )
    # Плата и процессор между собой по типу памяти тоже должны совпадать
    if b.cpu and b.motherboard and b.motherboard.memory_type not in b.cpu.memory_types:
        issues.append(
            Issue(
                Level.ERROR,
                "board_memory_cpu",
                f"Плата {b.motherboard.title} рассчитана на {b.motherboard.memory_type}, "
                f"а процессор {b.cpu.title} его не поддерживает.",
                _ids(b.motherboard, b.cpu),
            )
        )
    return issues


def ram_slots_and_capacity(b: Build) -> list[Issue]:
    if not (b.ram and b.motherboard):
        return []
    issues = []
    if b.ram.modules > b.motherboard.memory_slots:
        issues.append(
            Issue(
                Level.ERROR,
                "ram_slots",
                f"В комплекте {b.ram.title} {b.ram.modules} модуля, а на плате "
                f"{b.motherboard.title} только {b.motherboard.memory_slots} слота.",
                _ids(b.ram, b.motherboard),
            )
        )
    if b.ram.capacity_gb > b.motherboard.max_memory_gb:
        issues.append(
            Issue(
                Level.ERROR,
                "ram_capacity",
                f"Плата {b.motherboard.title} поддерживает до {b.motherboard.max_memory_gb} ГБ памяти, "
                f"а выбрано {b.ram.capacity_gb} ГБ.",
                _ids(b.ram, b.motherboard),
            )
        )
    return issues


# ---------- Накопители ----------


def m2_slots(b: Build) -> list[Issue]:
    if not b.motherboard:
        return []
    m2 = [s for s in b.storages if s.interface == "M.2"]
    if len(m2) > b.motherboard.m2_slots:
        return [
            Issue(
                Level.ERROR,
                "m2_slots",
                f"Выбрано {len(m2)} M.2-накопителя, а на плате {b.motherboard.title} "
                f"только {b.motherboard.m2_slots} слот(а) M.2.",
                _ids(*m2, b.motherboard),
            )
        ]
    return []


# ---------- Корпус ----------


def board_form_factor(b: Build) -> list[Issue]:
    if b.motherboard and b.case and b.motherboard.form_factor not in b.case.supported_form_factors:
        return [
            Issue(
                Level.ERROR,
                "form_factor",
                f"Плата {b.motherboard.title} формата {b.motherboard.form_factor} не помещается "
                f"в корпус {b.case.title} (поддерживает: {', '.join(b.case.supported_form_factors)}).",
                _ids(b.motherboard, b.case),
            )
        ]
    return []


def gpu_length(b: Build) -> list[Issue]:
    if b.gpu and b.case and b.gpu.length_mm > b.case.max_gpu_length_mm:
        return [
            Issue(
                Level.ERROR,
                "gpu_length",
                f"Видеокарта {b.gpu.title} (длина {b.gpu.length_mm} мм) не помещается "
                f"в корпус {b.case.title} (максимум {b.case.max_gpu_length_mm} мм).",
                _ids(b.gpu, b.case),
            )
        ]
    return []


def cooler_fits_case(b: Build) -> list[Issue]:
    if not (b.cooler and b.case):
        return []
    if b.cooler.kind == "air" and b.cooler.height_mm > b.case.max_cooler_height_mm:
        return [
            Issue(
                Level.ERROR,
                "cooler_height",
                f"Кулер {b.cooler.title} (высота {b.cooler.height_mm} мм) не помещается "
                f"в корпус {b.case.title} (максимум {b.case.max_cooler_height_mm} мм).",
                _ids(b.cooler, b.case),
            )
        ]
    if b.cooler.kind == "aio" and b.cooler.radiator_mm > b.case.max_radiator_mm:
        limit = f"максимум {b.case.max_radiator_mm} мм" if b.case.max_radiator_mm else "СЖО в него не устанавливается"
        return [
            Issue(
                Level.ERROR,
                "radiator_size",
                f"Радиатор СЖО {b.cooler.title} ({b.cooler.radiator_mm} мм) не помещается "
                f"в корпус {b.case.title} ({limit}).",
                _ids(b.cooler, b.case),
            )
        ]
    return []


# ---------- Питание ----------


def psu_power(b: Build) -> list[Issue]:
    if not b.psu:
        return []
    need = b.estimated_power_w
    if b.psu.wattage < need:
        return [
            Issue(
                Level.ERROR,
                "psu_insufficient",
                f"Блок питания {b.psu.title} ({b.psu.wattage} Вт) слабее расчётного потребления сборки ({need} Вт).",
                _ids(b.psu),
            )
        ]
    recommended = recommended_psu_w(b)
    if b.psu.wattage < recommended:
        return [
            Issue(
                Level.WARNING,
                "psu_low_headroom",
                f"Блок питания {b.psu.wattage} Вт работает почти на пределе: потребление сборки "
                f"около {need} Вт, рекомендуется не меньше {recommended} Вт.",
                _ids(b.psu),
            )
        ]
    return []


# ---------- Баланс ----------


def cpu_gpu_balance(b: Build, resolution: Resolution = Resolution.QHD) -> list[Issue]:
    """Предупреждение о дисбалансе в играх для заданного разрешения.

    Это правило не входит в RULES: check_build вызывает его отдельно, потому что ему
    нужно разрешение, а для неигровых сценариев проверка баланса отключается.
    """
    if not (b.cpu and b.gpu):
        return []
    balance = check_balance(b.cpu.perf_score, b.gpu.perf_score, resolution)
    if balance.kind == BalanceKind.CPU_WEAK:
        return [
            Issue(
                Level.WARNING,
                "cpu_bottleneck",
                f"Процессор {b.cpu.title} будет ограничивать видеокарту {b.gpu.title} в играх ({resolution}): "
                f"часть её производительности не раскроется.",
                _ids(b.cpu, b.gpu),
            )
        ]
    if balance.kind == BalanceKind.CPU_OVERKILL:
        return [
            Issue(
                Level.WARNING,
                "cpu_overkill",
                f"Процессор {b.cpu.title} заметно мощнее видеокарты {b.gpu.title}: в играх "
                f"упор будет в видеокарту, часть бюджета разумнее перенести на неё.",
                _ids(b.cpu, b.gpu),
            )
        ]
    return []


# Правила, которые проверяются всегда, в том числе для неполной сборки
RULES: list[Callable[[Build], list[Issue]]] = [
    cpu_motherboard_socket,
    cooler_socket,
    cooler_tdp,
    board_vrm,
    ram_type,
    ram_slots_and_capacity,
    m2_slots,
    board_form_factor,
    gpu_length,
    cooler_fits_case,
    psu_power,
]


# ---------- Проверки законченной сборки ----------


def missing_parts(b: Build) -> list[Issue]:
    names = {
        "cpu": "процессор",
        "motherboard": "материнская плата",
        "ram": "оперативная память",
        "psu": "блок питания",
        "case": "корпус",
    }
    issues = [
        Issue(Level.ERROR, "missing_part", f"Не выбран компонент: {name}.")
        for slot, name in names.items()
        if getattr(b, slot) is None
    ]
    if not b.storages:
        issues.append(Issue(Level.ERROR, "missing_part", "Не выбран компонент: накопитель."))
    return issues


def video_output(b: Build) -> list[Issue]:
    if b.cpu and not b.gpu and not b.cpu.has_igpu:
        return [
            Issue(
                Level.ERROR,
                "no_video",
                f"У процессора {b.cpu.title} нет встроенной графики: нужна дискретная видеокарта.",
                _ids(b.cpu),
            )
        ]
    return []


def cooling_present(b: Build) -> list[Issue]:
    if b.cpu and not b.cooler and not b.cpu.includes_cooler:
        return [
            Issue(
                Level.ERROR,
                "no_cooler",
                f"Процессор {b.cpu.title} продаётся без кулера: нужно выбрать охлаждение.",
                _ids(b.cpu),
            )
        ]
    return []


# Эти правила имеют смысл только когда пользователь считает сборку законченной:
# в процессе ручной сборки «нет видеокарты» — не ошибка, а следующий шаг
COMPLETE_BUILD_RULES: list[Callable[[Build], list[Issue]]] = [
    missing_parts,
    video_output,
    cooling_present,
]
