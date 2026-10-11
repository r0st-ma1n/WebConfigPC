"""Заполнение базы тестовыми данными: python -m app.seed

Скрипт идемпотентный: перед вставкой удаляет все комплектующие,
поэтому его можно запускать повторно.
"""
from collections import Counter

from sqlalchemy import delete

from app.db import SessionLocal
from app.models import Component
from app.seed import load_catalog


def main() -> None:
    parts = load_catalog()
    with SessionLocal() as session:
        # Строки дочерних таблиц удалятся каскадно (ondelete="CASCADE")
        session.execute(delete(Component))
        session.add_all(parts)
        session.commit()

    counts = Counter(p.category.value for p in parts)
    print(f"Добавлено комплектующих: {len(parts)}")
    for category, count in counts.items():
        print(f"  {category}: {count}")


if __name__ == "__main__":
    main()
