"""Обновление цен из внешних источников.

Источник цен — любой класс с методом fetch_prices(), возвращающим список PriceQuote
(протокол PriceProvider). Сейчас подключён прайс-лист в CSV (app/prices/csv_source.py);
парсер магазина или API поставщика добавляются так же.

Перед записью цены проверяются: слишком резкое изменение скорее говорит об ошибке
в выгрузке (лишний ноль, цена за упаковку), поэтому такая цена не применяется и попадает в отчёт.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol

from sqlalchemy.orm import Session

from app.models import Component
from app.repository import bump_catalog_version, load_parts

# На какую долю цена может измениться за одно обновление (0.5 — на 50%)
DEFAULT_MAX_CHANGE = 0.5


@dataclass
class PriceQuote:
    component_id: int
    price_rub: int
    source: str
    fetched_at: datetime = field(default_factory=datetime.now)


class PriceProvider(Protocol):
    """Интерфейс источника цен. В problems источник складывает строки, которые не смог разобрать."""

    name: str
    problems: list[str]

    def fetch_prices(self, components: list[Component]) -> list[PriceQuote]: ...


@dataclass
class PriceReport:
    changed: int = 0
    unchanged: int = 0
    # Цены, которые не применены из-за слишком резкого изменения
    suspicious: list[str] = field(default_factory=list)
    # Ошибки источника: нераспознанные строки, неизвестные детали
    problems: list[str] = field(default_factory=list)

    def summary(self) -> str:
        return (
            f"изменено: {self.changed}, без изменений: {self.unchanged}, "
            f"отклонено: {len(self.suspicious)}, ошибок в источнике: {len(self.problems)}"
        )


def apply_quotes(parts: list[Component], quotes: list[PriceQuote], max_change: float | None) -> PriceReport:
    """Применяет цены к деталям в памяти. max_change=None — без проверки резких изменений."""
    by_id = {p.id: p for p in parts}
    report = PriceReport()
    for quote in quotes:
        part = by_id.get(quote.component_id)
        if part is None or quote.price_rub <= 0:
            continue
        if part.price_rub == quote.price_rub:
            report.unchanged += 1
        elif max_change is not None and abs(quote.price_rub - part.price_rub) > part.price_rub * max_change:
            report.suspicious.append(f"{part.title}: {part.price_rub} → {quote.price_rub} ₽")
            continue
        else:
            part.price_rub = quote.price_rub
            report.changed += 1
        part.price_updated_at = quote.fetched_at
    return report


def update_prices(
    session: Session, provider: PriceProvider, *, max_change: float | None = DEFAULT_MAX_CHANGE, dry_run: bool = False
) -> PriceReport:
    """Загружает цены от провайдера и записывает их в базу (при dry_run — только отчёт)."""
    parts = load_parts(session)
    report = apply_quotes(parts, provider.fetch_prices(parts), max_change)
    report.problems = list(provider.problems)
    if dry_run:
        session.rollback()
    else:
        session.commit()
        bump_catalog_version()  # бэкенд перечитает каталог со следующего запроса
    return report
