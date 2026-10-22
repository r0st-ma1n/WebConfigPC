"""Сохранённые сборки: запись в базу и чтение по короткому коду из ссылки."""

import logging
import secrets

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import Component, SavedBuild, SavedBuildPart
from app.recommender import require_complete
from app.repository import build_from_ids
from app.schemas import RecommendIn, SaveBuildIn

log = logging.getLogger(__name__)

# 6 случайных байт — 8 символов base64url, 2^48 вариантов: код нельзя угадать перебором
SLUG_BYTES = 6
# Совпадение кодов почти невозможно, но уникальность всё равно проверяет база
SLUG_ATTEMPTS = 3


def create(session: Session, parts: list[Component], body: SaveBuildIn) -> SavedBuild:
    """Сохраняет сборку. Неизвестные детали — 404, неполная сборка — 422 (RecommendError)."""
    build = build_from_ids(parts, body.part_ids)
    require_complete(build)
    by_id = {p.id: p for p in parts}
    params = RecommendIn.model_validate(body.model_dump(include=set(RecommendIn.model_fields)))

    for attempt in range(1, SLUG_ATTEMPTS + 1):
        saved = SavedBuild(
            slug=secrets.token_urlsafe(SLUG_BYTES),
            params=params.model_dump(mode="json"),
            tier=body.tier.value if body.tier else None,
            parts=[
                SavedBuildPart(position=i, component_id=pid, price_rub=by_id[pid].price_rub)
                for i, pid in enumerate(body.part_ids)
            ],
        )
        session.add(saved)
        try:
            session.commit()
        except IntegrityError:
            session.rollback()
            if attempt == SLUG_ATTEMPTS:
                raise
            log.warning("Код сохранённой сборки уже занят, пробую другой")
            continue
        return saved
    raise AssertionError("unreachable")


def get(session: Session, slug: str) -> SavedBuild | None:
    return session.scalar(select(SavedBuild).where(SavedBuild.slug == slug))
