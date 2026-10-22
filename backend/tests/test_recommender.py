"""Тесты рекомендательной системы на реальном тестовом каталоге (без базы данных)."""

import itertools
from dataclasses import FrozenInstanceError
from functools import cache

import pytest

from app.balance import Resolution
from app.compatibility import check_build
from app.models import Category
from app.recommender import RecommendError, RecommendRequest, Scenario, Tier, recommend
from app.recommender.budget import budget_shares
from app.recommender.builder import AVOIDED_WARNINGS, BuildSearch, Catalog, pick
from app.recommender.params import MIN_VRAM_GB, TIER_BUDGET_FACTOR, Platform
from app.recommender.scoring import gaming_metric, ram_metric, score
from app.seed import load_catalog
from tests import factories as f

CATALOG = load_catalog(with_ids=True)
BY_NAME = {p.name: p for p in CATALOG}


@cache
def run(
    budget: int,
    scenario: Scenario,
    resolution: Resolution = Resolution.QHD,
    platform: Platform | None = None,
    cpu_id: int | None = None,
    gpu_id: int | None = None,
):
    """Подбор с кэшем: один и тот же запрос в разных тестах считается один раз."""
    return recommend(CATALOG, RecommendRequest(budget, scenario, resolution, platform, cpu_id, gpu_id))


TYPICAL_REQUESTS = [
    (60_000, Scenario.GAMING, Resolution.FHD),
    (120_000, Scenario.GAMING, Resolution.QHD),
    (250_000, Scenario.GAMING, Resolution.UHD),
    (150_000, Scenario.WORKSTATION, Resolution.QHD),
    (45_000, Scenario.OFFICE, Resolution.QHD),
]


# ---------- Распределение бюджета ----------


@pytest.mark.parametrize("scenario", list(Scenario))
@pytest.mark.parametrize("resolution", list(Resolution))
def test_budget_shares_sum_to_one(scenario, resolution):
    assert sum(budget_shares(scenario, resolution).values()) == pytest.approx(1.0)


def test_gpu_share_grows_with_resolution():
    shares = [budget_shares(Scenario.GAMING, r)[Category.GPU] for r in Resolution]
    assert shares == sorted(shares)


def test_office_budget_has_no_gpu_share():
    assert budget_shares(Scenario.OFFICE)[Category.GPU] == 0


# ---------- Модель оценки ----------


def test_gaming_performance_limited_by_weaker_part():
    req = RecommendRequest(100_000, Scenario.GAMING, Resolution.QHD)
    strong_gpu, weak_cpu = f.gpu(perf_score=66), f.cpu(perf_score=48)
    value, limiter = gaming_metric(f.full_build(cpu=weak_cpu, gpu=strong_gpu), req)
    assert limiter == "cpu"
    assert value == pytest.approx(48)  # K = 1.0 для 1440p: видеокарта не раскроется выше 48


def test_cpu_matters_less_in_4k():
    build = f.full_build(cpu=f.cpu(perf_score=48), gpu=f.gpu(perf_score=60))
    _, limiter_qhd = gaming_metric(build, RecommendRequest(100_000, Scenario.GAMING, Resolution.QHD))
    _, limiter_uhd = gaming_metric(build, RecommendRequest(100_000, Scenario.GAMING, Resolution.UHD))
    assert limiter_qhd == "cpu"
    assert limiter_uhd != "cpu"


def test_extra_ram_is_useless_for_gaming_but_useful_for_workstation():
    ram32 = f.full_build(ram=f.ram(capacity_gb=32))
    ram64 = f.full_build(ram=f.ram(capacity_gb=64))
    assert ram_metric(ram64, Scenario.GAMING) == ram_metric(ram32, Scenario.GAMING)
    assert ram_metric(ram64, Scenario.WORKSTATION) > ram_metric(ram32, Scenario.WORKSTATION)


def test_single_channel_ram_penalized_more_with_igpu():
    single, dual = f.ram(capacity_gb=16, modules=1), f.ram(capacity_gb=16, modules=2)
    with_gpu = ram_metric(f.full_build(ram=dual), Scenario.OFFICE) - ram_metric(
        f.full_build(ram=single), Scenario.OFFICE
    )
    igpu = ram_metric(f.full_build(ram=dual, gpu=None), Scenario.OFFICE) - ram_metric(
        f.full_build(ram=single, gpu=None), Scenario.OFFICE
    )
    assert igpu > with_gpu > 0


# ---------- Основные свойства подбора ----------


@pytest.mark.parametrize(("budget", "scenario", "resolution"), TYPICAL_REQUESTS)
def test_builds_are_compatible_and_within_tier_limits(budget, scenario, resolution):
    result = run(budget, scenario, resolution)
    assert 2 <= len(result.recommendations) <= 3
    for rec in result.recommendations:
        assert rec.build.total_price <= budget * TIER_BUDGET_FACTOR[rec.tier]
        check = check_build(rec.build, complete=True, balance_resolution=None)
        assert check.is_compatible, [e.message for e in check.errors]
        assert not {w.code for w in check.warnings} & AVOIDED_WARNINGS


@pytest.mark.parametrize(("budget", "scenario", "resolution"), TYPICAL_REQUESTS)
def test_more_expensive_tier_is_better(budget, scenario, resolution):
    recs = run(budget, scenario, resolution).recommendations
    for cheaper, pricier in itertools.pairwise(recs):
        assert pricier.build.total_price > cheaper.build.total_price
        assert pricier.score >= cheaper.score


def test_optimal_tier_always_present():
    for request in TYPICAL_REQUESTS:
        assert Tier.OPTIMAL in {r.tier for r in run(*request).recommendations}


def test_higher_budget_gives_better_build():
    def optimal_score(budget):
        return next(r.score for r in run(budget, Scenario.GAMING).recommendations if r.tier == Tier.OPTIMAL)

    assert optimal_score(80_000) < optimal_score(120_000) < optimal_score(200_000)


@pytest.mark.parametrize("budget", [80_000, 120_000, 200_000])
def test_gaming_builds_are_balanced(budget):
    """Оптимальная игровая сборка не должна заметно упираться в процессор."""
    rec = next(r for r in run(budget, Scenario.GAMING).recommendations if r.tier == Tier.OPTIMAL)
    assert "cpu_bottleneck" not in {w.code for w in rec.check.warnings}
    assert rec.breakdown.limiter != "cpu"


def test_office_build_uses_integrated_graphics():
    for rec in run(45_000, Scenario.OFFICE).recommendations:
        assert rec.build.gpu is None
        assert rec.build.cpu.has_igpu


def test_scenario_requirements():
    for rec in run(150_000, Scenario.WORKSTATION).recommendations:
        assert rec.build.ram.capacity_gb >= 32
        assert rec.build.gpu.vram_gb >= MIN_VRAM_GB
    for rec in run(120_000, Scenario.GAMING).recommendations:
        assert rec.build.ram.capacity_gb >= 32  # при бюджете от 90 тыс. — минимум 32 ГБ
        assert all(s.kind != "HDD" for s in rec.build.storages)
        assert rec.build.psu.efficiency.startswith("80+")


def test_workstation_prefers_multicore_cpu():
    """Для работы процессор выбирается по многопоточной производительности."""
    work = next(r for r in run(150_000, Scenario.WORKSTATION).recommendations if r.tier == Tier.OPTIMAL)
    game = next(r for r in run(150_000, Scenario.GAMING).recommendations if r.tier == Tier.OPTIMAL)
    assert work.build.cpu.multicore_score > game.build.cpu.multicore_score


# ---------- Предпочтения пользователя ----------


@pytest.mark.parametrize("platform", list(Platform))
def test_platform_preference(platform):
    for rec in run(120_000, Scenario.GAMING, platform=platform).recommendations:
        assert rec.build.cpu.brand.lower() == platform.value


def test_pinned_gpu_is_used_and_not_replaced():
    gpu = BY_NAME["GeForce RTX 5070 Infinity 3"]
    for rec in run(130_000, Scenario.GAMING, gpu_id=gpu.id).recommendations:
        assert rec.build.gpu.id == gpu.id
        assert all(a.category != Category.GPU for a in rec.upgrades + rec.savings)


def test_pinned_cpu_is_used():
    cpu = BY_NAME["Core Ultra 7 265K"]
    for rec in run(150_000, Scenario.WORKSTATION, cpu_id=cpu.id).recommendations:
        assert rec.build.cpu.id == cpu.id


def test_unknown_pinned_part():
    with pytest.raises(RecommendError, match="не найден"):
        recommend(CATALOG, RecommendRequest(100_000, Scenario.GAMING, cpu_id=999_999))


def test_too_small_budget_gives_clear_error():
    with pytest.raises(RecommendError, match=r"самая дешёвая подходящая сборка стоит"):
        recommend(CATALOG, RecommendRequest(20_000, Scenario.GAMING))


def test_zero_budget():
    with pytest.raises(RecommendError):
        recommend(CATALOG, RecommendRequest(0, Scenario.OFFICE))


# ---------- Замены ----------


@pytest.mark.parametrize(("budget", "scenario", "resolution"), TYPICAL_REQUESTS)
def test_alternatives_are_valid(budget, scenario, resolution):
    request = RecommendRequest(budget, scenario, resolution)
    search = BuildSearch(Catalog(CATALOG), request)
    for rec in run(budget, scenario, resolution).recommendations:
        base = score(rec.build, request)
        for alt in rec.upgrades + rec.savings:
            assert search.is_valid(alt.build), alt.text
            # Разница в цене и оценке посчитана правильно
            assert alt.price_delta == alt.build.total_price - rec.build.total_price
            assert alt.score_delta_pct == pytest.approx((score(alt.build, request) - base) / base * 100, abs=0.06)
            assert alt.build.part_in_slot(alt.category).id == alt.new_part.id
        for alt in rec.upgrades:
            assert alt.price_delta > 0 and alt.score_delta_pct >= 2
        for alt in rec.savings:
            assert alt.price_delta <= -1000 and alt.score_delta_pct >= -3


def test_cpu_change_with_other_socket_repairs_build():
    """Замена процессора AMD AM5 на Intel: плата и память подбираются заново, остальное не трогается."""
    request = RecommendRequest(120_000, Scenario.GAMING)
    search = BuildSearch(Catalog(CATALOG), request)
    build = next(r for r in run(120_000, Scenario.GAMING).recommendations if r.tier == Tier.HEADROOM).build
    assert build.cpu.socket == "AM5"
    intel = BY_NAME["Core i5-13400F"]

    repaired = search.repair(build.replace_part(intel), keep=intel)

    assert repaired is not None and search.is_valid(repaired)
    assert repaired.cpu.id == intel.id
    assert repaired.motherboard.socket == "LGA1700"
    assert repaired.gpu.id == build.gpu.id  # видеокарта осталась прежней


def test_some_alternatives_exist():
    rec = next(r for r in run(120_000, Scenario.GAMING).recommendations if r.tier == Tier.CHEAPER)
    assert rec.upgrades and rec.savings


# ---------- Объяснения ----------


def test_gaming_explanation_mentions_key_facts():
    rec = next(r for r in run(120_000, Scenario.GAMING).recommendations if r.tier == Tier.OPTIMAL)
    text = rec.explanation
    assert rec.build.gpu.title in text and rec.build.cpu.title in text
    assert "1440p" in text
    assert f"{rec.build.estimated_power_w} Вт" in text


def test_office_explanation_mentions_integrated_graphics():
    rec = run(45_000, Scenario.OFFICE).recommendations[0]
    assert "встроенной графики" in rec.explanation


def test_facts_are_json_serializable():
    import json

    for rec in run(120_000, Scenario.GAMING).recommendations:
        json.dumps(rec.facts, ensure_ascii=False)


# ---------- Сборка и выбор детали (на них опираются кэши подбора) ----------


def test_build_is_immutable_and_with_part_returns_new_build():
    build = f.full_build()
    price = build.total_price
    with pytest.raises(FrozenInstanceError):
        build.gpu = None  # type: ignore[misc]
    pricier = build.with_part(f.gpu(price_rub=90_000))
    assert build.total_price == price  # исходная сборка и её закэшированная цена не изменились
    assert pricier.total_price == price - 10_000 + 90_000
    assert pricier.key != build.key


def test_pick_without_limit_takes_best_of_cheapest():
    cheap_weak, cheap_strong, pricey = f.ram(price_rub=5000), f.ram(price_rub=5000), f.ram(price_rub=9000)
    value = {cheap_weak.id: 1, cheap_strong.id: 2, pricey.id: 10}
    assert pick([cheap_weak, cheap_strong, pricey], None, lambda r: value[r.id]) is cheap_strong
    # Укладывается в лимит — берётся самая полезная
    assert pick([cheap_weak, cheap_strong, pricey], 10_000, lambda r: value[r.id]) is pricey
