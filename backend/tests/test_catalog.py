"""Проверки тестового каталога: данных достаточно и они согласованы между собой."""

from collections import Counter

import pytest
from sqlalchemy import select
from sqlalchemy.exc import OperationalError

from app.db import SessionLocal
from app.models import Category, Component, Cpu, Motherboard, Ram
from app.seed import load_catalog

CATALOG = load_catalog(with_ids=True)


def test_each_category_has_15_to_25_items():
    counts = Counter(p.category for p in CATALOG)
    for category in Category:
        assert 15 <= counts[category] <= 25, category


def test_prices_and_scores_are_valid():
    for part in CATALOG:
        assert part.price_rub > 0, part
        assert 0 <= part.perf_score <= 100, part


def test_both_platforms_present():
    brands = {p.brand for p in CATALOG if isinstance(p, Cpu)}
    assert {"AMD", "Intel"} <= brands


def test_every_cpu_has_compatible_board_and_ram():
    """Для каждого процессора в каталоге есть подходящая плата и память."""
    boards = [p for p in CATALOG if isinstance(p, Motherboard)]
    rams = [p for p in CATALOG if isinstance(p, Ram)]
    for cpu in (p for p in CATALOG if isinstance(p, Cpu)):
        suitable = [b for b in boards if b.socket == cpu.socket and b.memory_type in cpu.memory_types]
        assert suitable, f"нет платы для {cpu.title}"
        assert any(r.memory_type == b.memory_type for b in suitable for r in rams)


def test_polymorphic_loading_from_db():
    """Из таблицы components SQLAlchemy создаёт объекты нужных подклассов."""
    try:
        with SessionLocal() as session:
            parts = session.scalars(select(Component)).all()
    except OperationalError:
        pytest.skip("PostgreSQL не запущен")
    if not parts:
        pytest.skip("база не заполнена (python -m app.seed)")
    cpus = [p for p in parts if p.category == Category.CPU]
    assert cpus and all(isinstance(p, Cpu) for p in cpus)
    # Поля дочерней таблицы доступны после закрытия сессии
    assert cpus[0].socket
