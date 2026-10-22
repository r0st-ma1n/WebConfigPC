"""Сохранённые сборки: ссылка, которой можно поделиться."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path
from sqlalchemy.orm import Session

from app import saved_builds
from app.db import get_session
from app.models import Component
from app.recommender import Tier, evaluate_build
from app.repository import build_from_ids, get_parts
from app.schemas import RecommendationOut, RecommendIn, SaveBuildIn, SaveBuildOut, SavedBuildOut

router = APIRouter(prefix="/api/builds", tags=["Сохранённые сборки"])

Slug = Annotated[str, Path(max_length=16, pattern=r"^[A-Za-z0-9_-]+$")]


@router.post("", status_code=201, response_model=SaveBuildOut)
def save_build(body: SaveBuildIn, session: Session = Depends(get_session), parts: list[Component] = Depends(get_parts)):
    saved = saved_builds.create(session, parts, body)
    return SaveBuildOut(slug=saved.slug)


@router.get("/{slug}", response_model=SavedBuildOut)
def get_saved_build(slug: Slug, session: Session = Depends(get_session), parts: list[Component] = Depends(get_parts)):
    """Сохранённая сборка, оценённая заново по текущим ценам каталога.
    Цена на момент сохранения возвращается отдельно — по ней видно, как изменилась стоимость."""
    saved = saved_builds.get(session, slug)
    if saved is None:
        raise HTTPException(404, "Сборка не найдена. Возможно, ссылка скопирована не полностью.")
    params = RecommendIn.model_validate(saved.params)
    build = build_from_ids(parts, [p.component_id for p in saved.parts])
    rec = evaluate_build(parts, params.to_request(), build, Tier(saved.tier) if saved.tier else None)
    return SavedBuildOut(
        slug=saved.slug,
        created_at=saved.created_at,
        params=params,
        saved_price=sum(p.price_rub for p in saved.parts),
        recommendation=RecommendationOut.from_rec(rec),
    )
