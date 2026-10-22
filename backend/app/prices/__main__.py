"""Импорт цен из CSV: python -m app.prices <файл.csv> [--dry-run] [--every СЕКУНДЫ]

С --every импорт повторяется по расписанию (так работает сервис prices в docker-compose):
поставщик кладёт новую выгрузку на место старой, и цены обновляются без перезапуска бэкенда —
каталог читается из базы при каждом запросе.
"""

import argparse
import logging
import time
from pathlib import Path

from sqlalchemy.exc import OperationalError

from app.config import settings
from app.db import SessionLocal
from app.observability import setup_logging
from app.prices.csv_source import CsvPriceProvider
from app.prices.provider import DEFAULT_MAX_CHANGE, update_prices

log = logging.getLogger("app.prices")


def run_once(path: Path, max_change: float | None, dry_run: bool) -> bool:
    """Один импорт. Возвращает False, если не удалось прочитать файл или подключиться к базе."""
    try:
        with SessionLocal() as session:
            report = update_prices(session, CsvPriceProvider(path), max_change=max_change, dry_run=dry_run)
    except (OSError, ValueError, OperationalError) as e:
        log.error("Импорт цен не выполнен: %s", e)
        return False
    log.info("Импорт цен%s: %s", " (пробный, без записи)" if dry_run else "", report.summary())
    for line in report.suspicious:
        log.warning("Цена не применена, слишком резкое изменение: %s", line)
    for line in report.problems:
        log.warning("Прайс-лист: %s", line)
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description="Импорт цен из прайс-листа в CSV")
    parser.add_argument("path", type=Path, help="CSV с колонками brand, name, price_rub")
    parser.add_argument("--dry-run", action="store_true", help="только показать отчёт, ничего не записывать")
    parser.add_argument("--every", type=int, metavar="СЕКУНДЫ", help="повторять импорт с этим интервалом")
    parser.add_argument(
        "--max-change",
        type=float,
        default=DEFAULT_MAX_CHANGE,
        help=f"максимальное изменение цены в долях (по умолчанию {DEFAULT_MAX_CHANGE}); 0 — без проверки",
    )
    args = parser.parse_args()
    setup_logging(settings.log_json, settings.log_level)
    max_change = args.max_change or None

    if not args.every:
        raise SystemExit(0 if run_once(args.path, max_change, args.dry_run) else 1)
    while True:
        # Ошибка одного запуска (файла ещё нет, база перезапускается) не останавливает расписание
        try:
            run_once(args.path, max_change, args.dry_run)
        except Exception:
            log.exception("Импорт цен завершился с ошибкой")
        time.sleep(args.every)


if __name__ == "__main__":
    main()
