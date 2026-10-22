"""Прайс-лист поставщика в CSV.

Обязательные колонки: brand, name, price_rub (остальные игнорируются). Разделитель — запятая,
точка с запятой (так сохраняет Excel с русской локалью) или табуляция. Цена может быть
записана как «12 990», «12990,00» или «12 990 ₽».

Детали ищутся по бренду и названию без учёта регистра и лишних пробелов, а не по id:
id меняются при повторном заполнении базы, а в выгрузке поставщика их нет.
"""

import csv
import re
from pathlib import Path

from app.models import Component
from app.prices.provider import PriceQuote

REQUIRED_COLUMNS = ("brand", "name", "price_rub")


def _key(brand: str, name: str) -> str:
    return " ".join(f"{brand} {name}".split()).casefold()


def _parse_price(value: str) -> int:
    cleaned = re.sub(r"[\s₽]", "", value).replace(",", ".")
    price = round(float(cleaned))
    if price <= 0:
        raise ValueError
    return price


class CsvPriceProvider:
    name = "csv"

    def __init__(self, path: Path):
        self.path = path
        self.problems: list[str] = []

    def read_rows(self) -> dict[str, int]:
        """Цены по ключу «бренд название». Ошибочные строки и повторы попадают в problems."""
        # utf-8-sig: Excel добавляет в начало файла BOM
        text = self.path.read_text(encoding="utf-8-sig")
        header = text.split("\n", 1)[0]
        reader = csv.DictReader(text.splitlines(), delimiter=max(";\t,", key=header.count))
        columns = [c.strip().lower() for c in reader.fieldnames or []]
        missing = [c for c in REQUIRED_COLUMNS if c not in columns]
        if missing:
            raise ValueError(f"{self.path.name}: нет колонок {', '.join(missing)}")
        reader.fieldnames = columns

        prices: dict[str, int] = {}
        for line, row in enumerate(reader, start=2):  # строка 1 — заголовок
            brand, name, raw_price = (row.get(c) or "" for c in REQUIRED_COLUMNS)
            if not brand.strip() or not name.strip():
                self.problems.append(f"строка {line}: не указан бренд или название")
                continue
            try:
                price = _parse_price(raw_price)
            except ValueError:
                self.problems.append(f"строка {line}: некорректная цена «{raw_price}»")
                continue
            key = _key(brand, name)
            if key in prices:
                self.problems.append(f"строка {line}: {brand} {name} уже встречалась, оставлена первая цена")
                continue
            prices[key] = price
        return prices

    def fetch_prices(self, components: list[Component]) -> list[PriceQuote]:
        self.problems = []
        prices = self.read_rows()
        by_key = {_key(c.brand, c.name): c for c in components}
        quotes = []
        for key, price in prices.items():
            part = by_key.get(key)
            if part is None:
                self.problems.append(f"нет в каталоге: {key}")
                continue
            quotes.append(PriceQuote(part.id, price, self.name))
        return quotes
