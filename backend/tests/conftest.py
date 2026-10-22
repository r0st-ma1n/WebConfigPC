"""Общие фикстуры тестов."""

import pytest
from sqlalchemy import exists, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.db import engine
from app.models import Component


@pytest.fixture
def session():
    """Сессия настоящего PostgreSQL (в CI он есть всегда), без базы тест пропускается.

    Тест идёт внутри транзакции, которая в конце откатывается: commit в коде
    приложения фиксирует только точку сохранения (SAVEPOINT), и база остаётся чистой."""
    try:
        connection = engine.connect()
    except OperationalError:
        pytest.skip("PostgreSQL не запущен")
    transaction = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint", expire_on_commit=False)
    try:
        if not session.scalar(select(exists().select_from(Component))):
            pytest.skip("база не заполнена (python -m app.seed)")
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()
