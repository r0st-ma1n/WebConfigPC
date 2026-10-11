"""Загрузка комплектующих из базы данных."""

from fastapi import Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_session
from app.domain import Build
from app.models import Component


def load_parts(session: Session) -> list[Component]:
    """Весь каталог одним запросом (JOIN со всеми таблицами характеристик).
    Каталог небольшой, поэтому подбор работает с ним целиком в памяти."""
    return list(session.scalars(select(Component).order_by(Component.category, Component.price_rub)))


def get_parts(session: Session = Depends(get_session)) -> list[Component]:
    """Зависимость FastAPI. В тестах подменяется каталогом из JSON."""
    return load_parts(session)


def build_from_ids(parts: list[Component], part_ids: list[int]) -> Build:
    by_id = {p.id: p for p in parts}
    unknown = [i for i in part_ids if i not in by_id]
    if unknown:
        raise HTTPException(404, f"Комплектующие не найдены: {unknown}")
    return Build.from_parts([by_id[i] for i in part_ids])
