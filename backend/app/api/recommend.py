"""Подбор сборок."""

from fastapi import APIRouter, Depends

from app.models import Component
from app.recommender import evaluate_build, recommend
from app.repository import build_from_ids, get_parts
from app.schemas import EvaluateIn, RecommendationOut, RecommendIn, RecommendOut

router = APIRouter(prefix="/api", tags=["Рекомендации"])


@router.post("/recommend", response_model=RecommendOut)
def recommend_builds(body: RecommendIn, parts: list[Component] = Depends(get_parts)):
    result = recommend(parts, body.to_request())
    return RecommendOut(
        allocation=dict(result.allocation),
        recommendations=[RecommendationOut.from_rec(r) for r in result.recommendations],
    )


@router.post("/recommend/evaluate", response_model=RecommendationOut)
def evaluate(body: EvaluateIn, parts: list[Component] = Depends(get_parts)):
    """Оценка конкретной сборки: используется, когда пользователь применяет замену."""
    build = build_from_ids(parts, body.part_ids)
    request = body.to_request()
    return RecommendationOut.from_rec(evaluate_build(parts, request, build))
