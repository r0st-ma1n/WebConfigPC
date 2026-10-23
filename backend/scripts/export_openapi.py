"""Выгрузка OpenAPI-схемы API в файл: python scripts/export_openapi.py [путь]

По этой схеме фронтенд генерирует TypeScript-типы (npm run gen:api). Схема и типы
лежат в репозитории, а CI проверяет, что они совпадают с текущим бэкендом: если поменять
Pydantic-схему и не обновить фронтенд, сборка упадёт.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # папка backend

from app.main import app

DEFAULT_PATH = Path(__file__).resolve().parents[2] / "frontend" / "openapi.json"


def main() -> None:
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_PATH
    schema = json.dumps(app.openapi(), ensure_ascii=False, indent=2) + "\n"
    path.write_text(schema, encoding="utf-8", newline="\n")
    print(f"OpenAPI-схема записана в {path}")


if __name__ == "__main__":
    main()
