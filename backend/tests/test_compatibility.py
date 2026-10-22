"""Тесты модуля совместимости: для каждого правила есть случай без нарушения и с нарушением."""

import pytest

from app.compatibility import Level, check_build, filter_compatible
from app.domain import Build
from tests import factories as f


def codes(build: Build, complete: bool = False) -> set[str]:
    return {i.code for i in check_build(build, complete=complete).issues}


def test_full_default_build_is_clean():
    result = check_build(f.full_build(), complete=True)
    assert result.issues == []
    assert result.is_compatible


# ---------- Сокеты и охлаждение ----------


def test_socket_mismatch():
    build = f.full_build(cpu=f.cpu(socket="LGA1700", memory_types=["DDR4", "DDR5"]))
    result = check_build(build)
    assert not result.is_compatible
    issue = next(i for i in result.issues if i.code == "socket_mismatch")
    assert "LGA1700" in issue.message and "AM5" in issue.message
    assert set(issue.part_ids) == {build.cpu.id, build.motherboard.id}


def test_cooler_socket_mismatch():
    build = f.full_build(cooler=f.cooler(sockets=["AM4", "LGA1700"]))
    assert "cooler_socket" in codes(build)


def test_cooler_socket_checked_against_board_when_no_cpu():
    build = Build(motherboard=f.motherboard(socket="LGA1851"), cooler=f.cooler(sockets=["AM5"]))
    assert "cooler_socket" in codes(build)


def test_weak_cooler_is_warning():
    build = f.full_build(cpu=f.cpu(power_w=250), cooler=f.cooler(max_tdp_w=150))
    result = check_build(build)
    issue = next(i for i in result.issues if i.code == "cooler_weak")
    assert issue.level == Level.WARNING
    assert result.is_compatible  # предупреждение не делает сборку несовместимой


# ---------- Память ----------


def test_ram_type_mismatch():
    build = f.full_build(ram=f.ram(memory_type="DDR4"))
    assert {"ram_type_board", "ram_type_cpu"} <= codes(build)


def test_intel_cpu_supports_both_memory_types():
    """LGA1700 работает и с DDR4, и с DDR5: тип памяти определяет плата."""
    build = f.full_build(
        cpu=f.cpu(socket="LGA1700", memory_types=["DDR4", "DDR5"]),
        motherboard=f.motherboard(socket="LGA1700", memory_type="DDR4"),
        ram=f.ram(memory_type="DDR4"),
    )
    assert check_build(build).is_compatible


def test_board_memory_type_not_supported_by_cpu():
    build = Build(cpu=f.cpu(memory_types=["DDR5"]), motherboard=f.motherboard(memory_type="DDR4"))
    assert "board_memory_cpu" in codes(build)


def test_ram_modules_exceed_slots():
    build = f.full_build(motherboard=f.motherboard(memory_slots=2), ram=f.ram(modules=4, capacity_gb=64))
    assert "ram_slots" in codes(build)


def test_ram_capacity_exceeds_board_limit():
    build = f.full_build(motherboard=f.motherboard(max_memory_gb=96), ram=f.ram(capacity_gb=128))
    assert "ram_capacity" in codes(build)


# ---------- Накопители ----------


def test_too_many_m2_drives():
    build = f.full_build(motherboard=f.motherboard(m2_slots=1), storages=[f.storage(), f.storage()])
    assert "m2_slots" in codes(build)


def test_sata_drives_do_not_use_m2_slots():
    hdd = f.storage(interface="SATA", kind="HDD")
    build = f.full_build(motherboard=f.motherboard(m2_slots=1), storages=[f.storage(), hdd])
    assert "m2_slots" not in codes(build)


# ---------- Корпус ----------


def test_board_form_factor_not_supported_by_case():
    build = f.full_build(case=f.case(supported_form_factors=["mATX", "ITX"]))
    issue = next(i for i in check_build(build).issues if i.code == "form_factor")
    assert "ATX" in issue.message


def test_gpu_too_long_for_case():
    build = f.full_build(gpu=f.gpu(length_mm=336), case=f.case(max_gpu_length_mm=315))
    issue = next(i for i in check_build(build).issues if i.code == "gpu_length")
    assert issue.level == Level.ERROR
    assert "336 мм" in issue.message and "315 мм" in issue.message


def test_gpu_exactly_fits_case():
    build = f.full_build(gpu=f.gpu(length_mm=315), case=f.case(max_gpu_length_mm=315))
    assert "gpu_length" not in codes(build)


def test_cooler_too_tall_for_case():
    build = f.full_build(cooler=f.cooler(height_mm=168), case=f.case(max_cooler_height_mm=160))
    assert "cooler_height" in codes(build)


def test_aio_radiator_must_fit_case():
    aio = f.cooler(kind="aio", height_mm=0, radiator_mm=360)
    assert "radiator_size" not in codes(f.full_build(cooler=aio, case=f.case(max_radiator_mm=360)))
    assert "radiator_size" in codes(f.full_build(cooler=aio, case=f.case(max_radiator_mm=240)))

    result = check_build(f.full_build(cooler=aio, case=f.case(max_radiator_mm=0)))
    issue = next(i for i in result.issues if i.code == "radiator_size")
    assert "не устанавливается" in issue.message


# ---------- Питание ----------


def test_psu_insufficient_is_error():
    result = check_build(f.full_build(psu=f.psu(wattage=300)))
    assert "psu_insufficient" in {e.code for e in result.errors}


def test_psu_low_headroom_is_warning():
    # Потребление сборки: 90 + 250 + 45 + 8 + 5 + 10 + 5 = 413 Вт. БП на 450 Вт хватает, но без запаса
    result = check_build(f.full_build(psu=f.psu(wattage=450)))
    assert result.estimated_power_w == 413
    assert "psu_low_headroom" in {w.code for w in result.warnings}
    assert result.is_compatible


def test_recommended_psu_respects_gpu_vendor_advice():
    # 413 × 1,3 = 537 → 550 Вт, но производитель видеокарты советует 650 Вт
    assert check_build(f.full_build()).recommended_psu_w == 650
    assert "psu_low_headroom" in codes(f.full_build(psu=f.psu(wattage=600)))


# ---------- Баланс CPU и GPU ----------


@pytest.mark.parametrize(
    ("cpu_score", "gpu_score", "expected"),
    [
        (48, 46, None),  # Ryzen 5 5600 + RTX 5070 — нормальная пара
        (48, 66, "cpu_bottleneck"),  # Ryzen 5 5600 + RTX 5080 — процессор ограничивает
        (100, 26, "cpu_overkill"),  # Ryzen 7 9800X3D + RTX 4060 — процессор избыточен
    ],
)
def test_cpu_gpu_balance(cpu_score, gpu_score, expected):
    build = f.full_build(cpu=f.cpu(perf_score=cpu_score), gpu=f.gpu(perf_score=gpu_score))
    found = codes(build) & {"cpu_bottleneck", "cpu_overkill"}
    assert found == ({expected} if expected else set())


# ---------- Законченная сборка ----------


def test_missing_parts_reported_only_for_complete_build():
    build = Build(cpu=f.cpu())
    assert check_build(build).issues == []
    assert "missing_part" in codes(build, complete=True)


def test_no_video_output():
    assert "no_video" in codes(f.full_build(gpu=None, cpu=f.cpu(has_igpu=False)), complete=True)
    assert "no_video" not in codes(f.full_build(gpu=None, cpu=f.cpu(has_igpu=True)), complete=True)


def test_cpu_without_box_cooler_needs_cooler():
    assert "no_cooler" in codes(f.full_build(cooler=None), complete=True)
    boxed = f.full_build(cooler=None, cpu=f.cpu(includes_cooler=True))
    assert "no_cooler" not in codes(boxed, complete=True)


# ---------- Фильтр для ручного режима ----------


def test_filter_compatible_boards_by_cpu():
    build = Build(cpu=f.cpu(socket="AM5"))
    am5 = f.motherboard(socket="AM5")
    am4 = f.motherboard(socket="AM4", memory_type="DDR4")
    lga = f.motherboard(socket="LGA1700")
    assert filter_compatible(build, [am5, am4, lga]) == [am5]


def test_filter_gpu_by_case_length():
    build = Build(case=f.case(max_gpu_length_mm=300))
    short, long_ = f.gpu(length_mm=280), f.gpu(length_mm=320)
    assert filter_compatible(build, [short, long_]) == [short]


def test_filter_ignores_existing_problems_of_other_parts():
    """Если в сборке уже есть конфликт (длинная видеокарта в коротком корпусе),
    подходящие процессоры всё равно не скрываются."""
    build = f.full_build(cpu=None, gpu=f.gpu(length_mm=400))
    good_cpu = f.cpu()
    assert filter_compatible(build, [good_cpu]) == [good_cpu]
