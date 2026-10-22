"""Оценка сборки под сценарий пользователя.

Итоговая оценка (0–100) — взвешенная сумма оценок по «ролям»:

    score = Σ вес(сценарий, роль) × оценка(роль)

Роли:
- gaming     — игровая производительность связки CPU+GPU (только для игр, см. ниже);
- cpu        — процессор (в играх — игровая оценка, в работе — многопоточная);
- gpu        — видеокарта (для работы с 3D);
- ram        — память: объём до полезного для сценария предела + частота + двухканальность;
- storage    — накопитель: объём до полезного предела + скорость по типу;
- platform   — среднее качество платы, блока питания, корпуса и охлаждения.

Игровая производительность. Число кадров ограничивает более слабое звено:
процессор готовит кадры, видеокарта их рисует. Поэтому

    gaming = min(gpu_score, cpu_score / K(разрешение))

где K — коэффициент из balance.py (чем выше разрешение, тем меньше нагрузка
на процессор). Деньги, вложенные в видеокарту сверх возможностей процессора
(или в процессор сверх возможностей видеокарты), оценку не повышают, поэтому
алгоритм сам выбирает сбалансированные пары.
"""

from dataclasses import dataclass

from app.balance import BALANCE_TOLERANCE, CPU_REQUIRED_FACTOR
from app.domain import Build
from app.recommender.params import RecommendRequest, Scenario

WEIGHTS: dict[Scenario, dict[str, float]] = {
    # Небольшой отдельный вес процессора в играх: он влияет на плавность (1% low),
    # стриминг и фоновые задачи, даже когда упор в видеокарту
    Scenario.GAMING: {"gaming": 0.80, "cpu": 0.05, "gpu": 0.0, "ram": 0.07, "storage": 0.05, "platform": 0.03},
    Scenario.WORKSTATION: {"gaming": 0.0, "cpu": 0.34, "gpu": 0.34, "ram": 0.16, "storage": 0.11, "platform": 0.05},
    Scenario.OFFICE: {"gaming": 0.0, "cpu": 0.50, "gpu": 0.0, "ram": 0.20, "storage": 0.25, "platform": 0.05},
}

ROLE_TITLES = {
    "gaming": "производительность в играх",
    "cpu": "процессор",
    "gpu": "видеокарта",
    "ram": "память",
    "storage": "накопитель",
    "platform": "плата, БП, корпус, охлаждение",
}

# Объём, больше которого в сценарии уже нет заметной пользы
USEFUL_RAM_GB = {Scenario.GAMING: 32, Scenario.WORKSTATION: 128, Scenario.OFFICE: 16}
USEFUL_STORAGE_GB = {Scenario.GAMING: 2000, Scenario.WORKSTATION: 4000, Scenario.OFFICE: 1000}
# Скорость накопителя по типу. Разница между бюджетным и топовым NVMe
# в играх и офисе почти незаметна, поэтому все NVMe считаются одинаково быстрыми
STORAGE_SPEED = {"HDD": 0.1, "SATA_SSD": 0.45, "NVMe": 1.0}
# В программах для 3D и видео (Blender, DaVinci Resolve) видеокарты NVIDIA
# заметно быстрее за счёт CUDA/OptiX, поэтому остальные учитываются с понижением
NON_NVIDIA_WORKSTATION_FACTOR = 0.8
# Условная оценка боксового кулера, когда отдельный кулер не выбран
BOX_COOLER_SCORE = 40


def cpu_metric(build: Build, scenario: Scenario) -> float:
    """Какая производительность процессора важна в сценарии."""
    cpu = build.cpu
    if cpu is None:
        return 0
    if scenario == Scenario.GAMING:
        return cpu.perf_score  # игровая производительность
    if scenario == Scenario.WORKSTATION:
        return cpu.multicore_score  # рендер и кодирование используют все ядра
    return (cpu.perf_score + cpu.multicore_score) / 2  # офис: общая отзывчивость


def gaming_metric(build: Build, request: RecommendRequest) -> tuple[float, str | None]:
    """Игровая производительность связки и её ограничитель: "cpu", "gpu" или None (баланс)."""
    if build.gpu is None or build.cpu is None:
        return 0, None
    gpu = build.gpu.perf_score
    cpu_limit = build.cpu.perf_score / CPU_REQUIRED_FACTOR[request.resolution]
    if cpu_limit < gpu * (1 - BALANCE_TOLERANCE):
        return cpu_limit, "cpu"
    if gpu < cpu_limit * (1 - BALANCE_TOLERANCE):
        return gpu, "gpu"
    return gpu, None


def gpu_metric(build: Build, scenario: Scenario) -> float:
    """Видеокарта в рабочих задачах (рендер на GPU, ускорение монтажа)."""
    gpu = build.gpu
    if gpu is None:
        return 0
    is_nvidia = gpu.chip.startswith(("RTX", "GTX"))
    factor = 1.0 if is_nvidia or scenario != Scenario.WORKSTATION else NON_NVIDIA_WORKSTATION_FACTOR
    return gpu.perf_score * factor


def ram_metric(build: Build, scenario: Scenario) -> float:
    """75% — объём (до полезного предела), 15% — частота (6000 МГц и выше — максимум),
    10% — двухканальный режим (нужно два и более модуля).

    Встроенная графика использует оперативную память как видеопамять, и в одноканальном
    режиме теряет до половины скорости. Поэтому без видеокарты штраф за один модуль больше.
    """
    ram = build.ram
    if ram is None:
        return 0
    volume = min(ram.capacity_gb / USEFUL_RAM_GB[scenario], 1)
    speed = min(ram.speed_mhz / 6000, 1)
    value = 75 * volume + 15 * speed + 10
    if ram.modules < 2:
        value -= 10 if build.gpu else 30
    return value


def storage_metric(build: Build, scenario: Scenario) -> float:
    """Половина — суммарный объём (до полезного предела), половина — скорость лучшего диска."""
    if not build.storages:
        return 0
    total = sum(s.capacity_gb for s in build.storages)
    volume = min(total / USEFUL_STORAGE_GB[scenario], 1)
    speed = max(STORAGE_SPEED[s.kind] for s in build.storages)
    return 50 * volume + 50 * speed


def platform_quality(build: Build) -> float:
    scores = [p.perf_score for p in (build.motherboard, build.psu, build.case, build.cooler) if p]
    if build.cooler is None:
        scores.append(BOX_COOLER_SCORE)
    return sum(scores) / len(scores)


@dataclass
class ScoreBreakdown:
    contributions: dict[str, float]  # вклад каждой роли в итоговую оценку
    limiter: str | None  # в играх: что ограничивает FPS — "cpu", "gpu" или None (баланс)

    @property
    def total(self) -> float:
        return sum(self.contributions.values())


def score_breakdown(build: Build, request: RecommendRequest) -> ScoreBreakdown:
    weights = WEIGHTS[request.scenario]
    gaming, limiter = gaming_metric(build, request) if request.is_gaming else (0, None)
    raw = {
        "gaming": gaming,
        "cpu": cpu_metric(build, request.scenario),
        "gpu": gpu_metric(build, request.scenario),
        "ram": ram_metric(build, request.scenario),
        "storage": storage_metric(build, request.scenario),
        "platform": platform_quality(build),
    }
    return ScoreBreakdown({role: weights[role] * value for role, value in raw.items() if weights[role]}, limiter)


def score(build: Build, request: RecommendRequest) -> float:
    return score_breakdown(build, request).total


# Современные платформы, на которые ещё будут выходить процессоры
CURRENT_SOCKETS = {"AM5", "LGA1851"}


def future_proof_bonus(build: Build) -> float:
    """Бонус для варианта «С запасом»: возможность апгрейда в будущем.

    +3 за актуальный сокет (можно поменять процессор без смены платы),
    +2 за блок питания с запасом 50% (хватит на более мощную видеокарту),
    +1 за свободные слоты памяти (можно добавить ОЗУ).
    """
    bonus = 0.0
    if build.cpu and build.cpu.socket in CURRENT_SOCKETS:
        bonus += 3
    if build.psu and build.psu.wattage >= build.estimated_power_w * 1.5:
        bonus += 2
    if build.motherboard and build.ram and build.motherboard.memory_slots > build.ram.modules:
        bonus += 1
    return bonus
