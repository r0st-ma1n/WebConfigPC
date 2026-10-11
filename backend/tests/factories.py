"""Фабрики деталей для тестов. Значения по умолчанию дают совместимую сборку,
в тесте меняется только то, что проверяется."""
from itertools import count

from app.domain import Build
from app.models import Case, Cooler, Cpu, Gpu, Motherboard, Psu, Ram, Storage

_ids = count(1)


def _make(model, defaults: dict, overrides: dict):
    data = {"brand": "Test", "price_rub": 10000, "perf_score": 50, "power_w": 0, **defaults, **overrides}
    return model(id=next(_ids), **data)


def cpu(**kw) -> Cpu:
    return _make(Cpu, dict(
        name="CPU", power_w=90, socket="AM5", cores=6, threads=12, base_ghz=3.8, boost_ghz=5.0,
        memory_types=["DDR5"], has_igpu=False, includes_cooler=False, multicore_score=45,
    ), kw)


def gpu(**kw) -> Gpu:
    return _make(Gpu, dict(
        name="GPU", chip="GPU", perf_score=46, power_w=250, vram_gb=12, length_mm=300,
        recommended_psu_w=650,
    ), kw)


def motherboard(**kw) -> Motherboard:
    return _make(Motherboard, dict(
        name="Board", power_w=45, socket="AM5", chipset="B650", form_factor="ATX",
        memory_type="DDR5", memory_slots=4, max_memory_gb=192, m2_slots=2,
    ), kw)


def ram(**kw) -> Ram:
    return _make(Ram, dict(
        name="RAM", power_w=8, memory_type="DDR5", capacity_gb=32, modules=2, speed_mhz=6000,
    ), kw)


def storage(**kw) -> Storage:
    return _make(Storage, dict(name="SSD", power_w=5, kind="NVMe", interface="M.2", capacity_gb=1000), kw)


def psu(**kw) -> Psu:
    return _make(Psu, dict(name="PSU", wattage=750, efficiency="80+ Gold"), kw)


def case(**kw) -> Case:
    return _make(Case, dict(
        name="Case", power_w=10, supported_form_factors=["ATX", "mATX", "ITX"],
        max_gpu_length_mm=360, max_cooler_height_mm=165, max_radiator_mm=360,
    ), kw)


def cooler(**kw) -> Cooler:
    return _make(Cooler, dict(
        name="Cooler", power_w=5, kind="air", height_mm=155, radiator_mm=0,
        sockets=["AM4", "AM5", "LGA1700", "LGA1851"], max_tdp_w=220,
    ), kw)


def full_build(**overrides) -> Build:
    """Полная совместимая сборка. overrides заменяют отдельные детали,
    например full_build(case=case(max_gpu_length_mm=280))."""
    parts = dict(
        cpu=cpu(), gpu=gpu(), motherboard=motherboard(), ram=ram(), storages=[storage()],
        psu=psu(), case=case(), cooler=cooler(),
    )
    parts.update(overrides)
    return Build(**parts)
