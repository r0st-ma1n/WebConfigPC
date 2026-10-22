"""Рекомендательная система: подбор сборок, замены и объяснения.

Точки входа:
- recommend(parts, request) — подобрать 2–3 сборки под запрос;
- evaluate_build(parts, request, build) — оценить произвольную сборку
  (например, после того как пользователь применил замену).
"""

from dataclasses import dataclass

from app.compatibility import CheckResult, check_build
from app.domain import Build
from app.models import Category, Component
from app.recommender.alternatives import Alternative, find_alternatives
from app.recommender.budget import allocate_budget
from app.recommender.builder import BuildSearch, Catalog
from app.recommender.explain import build_facts, template_explanation
from app.recommender.params import (
    TIER_TITLES,
    Platform,
    RecommendError,
    RecommendRequest,
    Scenario,
    Tier,
)
from app.recommender.scoring import ScoreBreakdown, score_breakdown

__all__ = [
    "Platform",
    "RecommendError",
    "RecommendRequest",
    "Recommendation",
    "RecommendationResult",
    "Scenario",
    "Tier",
    "evaluate_build",
    "recommend",
]


@dataclass
class Recommendation:
    tier: Tier | None
    title: str
    build: Build
    breakdown: ScoreBreakdown
    check: CheckResult
    upgrades: list[Alternative]
    savings: list[Alternative]
    facts: dict
    explanation: str

    @property
    def score(self) -> float:
        return self.breakdown.total


@dataclass
class RecommendationResult:
    request: RecommendRequest
    allocation: dict[Category, int]  # плановое распределение бюджета по категориям
    recommendations: list[Recommendation]


def recommend(parts: list[Component], request: RecommendRequest) -> RecommendationResult:
    if request.budget <= 0:
        raise RecommendError("Бюджет должен быть больше нуля.")
    search = BuildSearch(Catalog(parts), request)
    builds = search.search()
    return RecommendationResult(
        request=request,
        allocation=allocate_budget(request.budget, request.scenario, request.resolution),
        recommendations=[_describe(search, build, tier) for tier, build in builds.items()],
    )


def evaluate_build(
    parts: list[Component], request: RecommendRequest, build: Build, tier: Tier | None = None
) -> Recommendation:
    """Описание произвольной сборки в том же виде, что и рекомендации."""
    require_complete(build)
    return _describe(BuildSearch(Catalog(parts), request), build, tier)


def require_complete(build: Build) -> None:
    """RecommendError, если в сборке не хватает деталей."""
    missing = [i.message for i in check_build(build, complete=True).errors if i.code == "missing_part"]
    if missing:
        raise RecommendError("Сборка неполная. " + " ".join(missing))


def _describe(search: BuildSearch, build: Build, tier: Tier | None) -> Recommendation:
    request = search.request
    breakdown = score_breakdown(build, request)
    check = check_build(build, complete=True, balance_resolution=request.resolution if request.is_gaming else None)
    upgrades, savings = find_alternatives(search, build) if check.is_compatible else ([], [])
    facts = build_facts(
        request, tier, build, breakdown, check, [a.as_fact() for a in upgrades], [a.as_fact() for a in savings]
    )
    return Recommendation(
        tier=tier,
        title=TIER_TITLES[tier] if tier else "Ваша сборка",
        build=build,
        breakdown=breakdown,
        check=check,
        upgrades=upgrades,
        savings=savings,
        facts=facts,
        explanation=template_explanation(facts),
    )
