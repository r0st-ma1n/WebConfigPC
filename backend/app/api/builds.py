"""Сохранённые сборки: ссылка, которой можно поделиться, и список «Мои сборки»."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Response
from sqlalchemy.orm import Session

from app import saved_builds
from app.auth import current_user, optional_user
from app.db import get_session
from app.models import Component, SavedBuild, User
from app.recommender import TIER_TITLES, Tier, evaluate_build
from app.repository import build_from_ids, get_parts
from app.schemas import (
    RecommendationOut,
    RecommendIn,
    SaveBuildIn,
    SaveBuildOut,
    SavedBuildOut,
    SavedBuildSummaryOut,
)

router = APIRouter(prefix="/api/builds", tags=["Сохранённые сборки"])

Slug = Annotated[str, Path(max_length=16, pattern=r"^[A-Za-z0-9_-]+$")]
NOT_FOUND = "Сборка не найдена. Возможно, ссылка скопирована не полностью."


@router.post("", status_code=201, response_model=SaveBuildOut)
def save_build(
    body: SaveBuildIn,
    session: Session = Depends(get_session),
    parts: list[Component] = Depends(get_parts),
    user: User | None = Depends(optional_user),
):
    """Сохранить может и гость; сборка вошедшего пользователя попадает в «Мои сборки»."""
    saved = saved_builds.create(session, parts, body, owner=user)
    return SaveBuildOut(slug=saved.slug)


@router.get("", response_model=list[SavedBuildSummaryOut])
def my_builds(session: Session = Depends(get_session), user: User = Depends(current_user)):
    return [
        SavedBuildSummaryOut(
            slug=s.slug,
            created_at=s.created_at,
            title=TIER_TITLES[Tier(s.tier)] if s.tier else "Ваша сборка",
            params=RecommendIn.model_validate(s.params),
            saved_price=sum(p.price_rub for p in s.parts),
        )
        for s in saved_builds.list_owned(session, user)
    ]


@router.get("/{slug}", response_model=SavedBuildOut)
def get_saved_build(
    slug: Slug,
    session: Session = Depends(get_session),
    parts: list[Component] = Depends(get_parts),
    user: User | None = Depends(optional_user),
):
    """Сохранённая сборка, оценённая заново по текущим ценам каталога.
    Цена на момент сохранения возвращается отдельно — по ней видно, как изменилась стоимость."""
    saved = _get_or_404(session, slug)
    params = RecommendIn.model_validate(saved.params)
    build = build_from_ids(parts, [p.component_id for p in saved.parts])
    rec = evaluate_build(parts, params.to_request(), build, Tier(saved.tier) if saved.tier else None)
    return SavedBuildOut(
        slug=saved.slug,
        created_at=saved.created_at,
        params=params,
        saved_price=sum(p.price_rub for p in saved.parts),
        recommendation=RecommendationOut.from_rec(rec),
        owned=user is not None and saved.user_id == user.id,
    )


@router.delete("/{slug}", status_code=204)
def delete_build(slug: Slug, session: Session = Depends(get_session), user: User = Depends(current_user)):
    saved = _get_or_404(session, slug)
    # Ссылкой могли поделиться, поэтому сам факт существования сборки не секрет — честный 403
    if saved.user_id != user.id:
        raise HTTPException(403, "Удалить можно только свою сборку.")
    saved_builds.delete(session, saved)
    return Response(status_code=204)


def _get_or_404(session: Session, slug: str) -> SavedBuild:
    saved = saved_builds.get(session, slug)
    if saved is None:
        raise HTTPException(404, NOT_FOUND)
    return saved
