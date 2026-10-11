"""Модуль обновления цен — заглушка с готовым интерфейсом.

Сейчас цены хранятся в базе и заполняются из тестовых данных. Чтобы подключить
реальный источник (парсер магазина, API поставщика, выгрузку CSV), достаточно:
1. Написать класс с методом fetch_prices(), возвращающим список PriceQuote.
2. Передать его в update_prices().

Пример будущего парсера:

    class ShopParser:
        name = "shop"

        def fetch_prices(self, components):
            quotes = []
            for c in components:
                price = ...  # найти товар по c.brand + c.name и получить цену
                quotes.append(PriceQuote(c.id, price, self.name))
            return quotes
"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol

from sqlalchemy.orm import Session

from app.models import Component
from app.repository import load_parts


@dataclass
class PriceQuote:
    component_id: int
    price_rub: int
    source: str
    fetched_at: datetime = field(default_factory=datetime.now)


class PriceProvider(Protocol):
    """Интерфейс источника цен."""

    name: str

    def fetch_prices(self, components: list[Component]) -> list[PriceQuote]: ...


class StaticPriceProvider:
    """Заглушка: возвращает текущие цены из базы, ничего не меняя."""

    name = "static"

    def fetch_prices(self, components: list[Component]) -> list[PriceQuote]:
        return [PriceQuote(c.id, c.price_rub, self.name) for c in components]


def update_prices(session: Session, provider: PriceProvider) -> int:
    """Применяет цены от провайдера к базе. Возвращает число изменённых позиций."""
    parts = {p.id: p for p in load_parts(session)}
    changed = 0
    for quote in provider.fetch_prices(list(parts.values())):
        part = parts.get(quote.component_id)
        if part is None or quote.price_rub <= 0:
            continue
        if part.price_rub != quote.price_rub:
            part.price_rub = quote.price_rub
            changed += 1
        part.price_updated_at = quote.fetched_at
    session.commit()
    return changed
