"""Баланс процессора и видеокарты в играх.

Шкалы оценок разные: у GPU 100 = RTX 5090, у CPU 100 = Ryzen 7 9800X3D.
Видеокарты по скорости различаются сильнее процессоров, поэтому сравнивать
оценки один к одному нельзя. Используется коэффициент:

    процессор не ограничивает видеокарту, если  cpu_score >= gpu_score × K(разрешение)

Чем выше разрешение, тем больше нагрузка ложится на видеокарту и тем
слабее процессор может быть без потери кадров. Отсюда разные K.
Значения подобраны по известным связкам для 1440p: Ryzen 5 5600 + RTX 5070,
Ryzen 5 7500F + RX 9070 XT, Ryzen 7 9800X3D + RTX 5090 — сбалансированные пары,
а Ryzen 5 5600 + RTX 5080 уже упирается в процессор.
"""
from dataclasses import dataclass
from enum import StrEnum


class Resolution(StrEnum):
    FHD = "1080p"
    QHD = "1440p"
    UHD = "4k"


CPU_REQUIRED_FACTOR: dict[Resolution, float] = {
    Resolution.FHD: 1.2,
    Resolution.QHD: 1.0,
    Resolution.UHD: 0.7,
}

# Если процессор в столько раз «быстрее» видеокарты, деньги на CPU потрачены впустую
CPU_OVERKILL_RATIO = 2.7
# Разница меньше 3% незаметна на практике: такая пара считается сбалансированной
BALANCE_TOLERANCE = 0.03


class BalanceKind(StrEnum):
    OK = "ok"
    CPU_WEAK = "cpu_weak"  # процессор будет ограничивать видеокарту
    CPU_OVERKILL = "cpu_overkill"  # процессор избыточен для этой видеокарты


@dataclass
class Balance:
    kind: BalanceKind
    # Насколько процессор не дотягивает до нужного уровня (0..1), для штрафа в оценке сборки
    shortfall: float = 0.0


def check_balance(cpu_score: int, gpu_score: int, resolution: Resolution = Resolution.QHD) -> Balance:
    required = gpu_score * CPU_REQUIRED_FACTOR[resolution]
    if cpu_score < required * (1 - BALANCE_TOLERANCE):
        return Balance(BalanceKind.CPU_WEAK, shortfall=(required - cpu_score) / required)
    if cpu_score > gpu_score * CPU_OVERKILL_RATIO:
        return Balance(BalanceKind.CPU_OVERKILL)
    return Balance(BalanceKind.OK)
