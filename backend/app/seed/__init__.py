"""Тестовые данные каталога комплектующих."""
import json
from pathlib import Path

from app.models import MODEL_BY_CATEGORY, Category, Component

DATA_FILE = Path(__file__).with_name("components.json")


def load_catalog(with_ids: bool = False) -> list[Component]:
    """Читает components.json и создаёт ORM-объекты (пока не привязанные к базе).

    with_ids=True проставляет id вручную: так каталог можно использовать
    в тестах без PostgreSQL. При записи в базу id назначает сама БД.
    """
    raw = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    parts: list[Component] = []
    for category_value, items in raw.items():
        model = MODEL_BY_CATEGORY[Category(category_value)]
        for item in items:
            part = model(**item)
            if with_ids:
                part.id = len(parts) + 1
            parts.append(part)
    return parts
