"""Заполнение базы тестовыми данными: python -m app.seed [--if-empty]

Скрипт идемпотентный: перед вставкой удаляет все комплектующие,
поэтому его можно запускать повторно. С --if-empty база заполняется,
только если она пустая (так делает контейнер бэкенда при каждом запуске).
"""
import argparse
from collections import Counter

from sqlalchemy import delete, exists, select

from app.db import SessionLocal
from app.models import Component
from app.seed import load_catalog


def main() -> None:
    parser = argparse.ArgumentParser(description="Заполнение базы тестовыми данными")
    parser.add_argument("--if-empty", action="store_true", help="ничего не делать, если комплектующие уже есть")
    args = parser.parse_args()

    parts = load_catalog()
    with SessionLocal() as session:
        if args.if_empty and session.scalar(select(exists().select_from(Component))):
            print("База уже заполнена, пропускаю")
            return
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
