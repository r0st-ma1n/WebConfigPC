"""Импорт цен из прайс-листа в CSV."""

import logging

import pytest

from app.models import Category, Component
from app.prices.__main__ import run_once
from app.prices.csv_source import CsvPriceProvider
from app.prices.provider import PriceQuote, apply_quotes, update_prices
from app.repository import load_parts
from app.seed import load_catalog


@pytest.fixture
def catalog() -> list[Component]:
    return load_catalog(with_ids=True)


def first(parts: list[Component], category: Category) -> Component:
    return next(p for p in parts if p.category == category)


def write_csv(tmp_path, text: str, encoding: str = "utf-8"):
    path = tmp_path / "prices.csv"
    path.write_text(text, encoding=encoding)
    return path


def test_reads_excel_style_file(tmp_path, catalog):
    """Точка с запятой, BOM, цена с пробелами, копейками и знаком рубля, другой регистр."""
    cpu, gpu = first(catalog, Category.CPU), first(catalog, Category.GPU)
    path = write_csv(
        tmp_path,
        "Brand;Name;Price_RUB;sku\n"
        f"{cpu.brand.upper()};  {cpu.name} ;12 990 ₽;A-1\n"
        f"{gpu.brand};{gpu.name};25990,60;A-2\n",
        encoding="utf-8-sig",
    )
    provider = CsvPriceProvider(path)

    quotes = provider.fetch_prices(catalog)

    assert {(q.component_id, q.price_rub) for q in quotes} == {(cpu.id, 12_990), (gpu.id, 25_991)}
    assert provider.problems == []


def test_bad_rows_are_reported_and_skipped(tmp_path, catalog):
    cpu = first(catalog, Category.CPU)
    path = write_csv(
        tmp_path,
        "brand,name,price_rub\n"
        f"{cpu.brand},{cpu.name},10000\n"
        f"{cpu.brand},{cpu.name},11000\n"
        "Noname,Turbo 9000,5000\n"
        f"{cpu.brand},{cpu.name} X,по запросу\n"
        ",,100\n",
    )
    provider = CsvPriceProvider(path)

    quotes = provider.fetch_prices(catalog)

    assert [(q.component_id, q.price_rub) for q in quotes] == [(cpu.id, 10_000)]
    assert provider.problems == [
        f"строка 3: {cpu.brand} {cpu.name} уже встречалась, оставлена первая цена",
        "строка 5: некорректная цена «по запросу»",
        "строка 6: не указан бренд или название",
        "нет в каталоге: noname turbo 9000",
    ]


def test_missing_columns_rejected(tmp_path, catalog):
    path = write_csv(tmp_path, "brand,title,price\nAMD,Ryzen,1000\n")
    with pytest.raises(ValueError, match="нет колонок name, price_rub"):
        CsvPriceProvider(path).fetch_prices(catalog)


def test_sharp_price_change_is_not_applied(catalog):
    cpu, gpu, ram = first(catalog, Category.CPU), first(catalog, Category.GPU), first(catalog, Category.RAM)
    old_gpu = gpu.price_rub
    quotes = [
        PriceQuote(cpu.id, cpu.price_rub, "test"),
        PriceQuote(gpu.id, old_gpu * 10, "test"),  # лишний ноль в выгрузке
        PriceQuote(ram.id, ram.price_rub + 500, "test"),
    ]

    report = apply_quotes(catalog, quotes, max_change=0.5)

    assert (report.changed, report.unchanged) == (1, 1)
    assert report.suspicious == [f"{gpu.title}: {old_gpu} → {old_gpu * 10} ₽"]
    assert gpu.price_rub == old_gpu

    assert apply_quotes(catalog, quotes[1:2], max_change=None).changed == 1
    assert gpu.price_rub == old_gpu * 10


def test_update_prices_writes_to_database(session, tmp_path):
    cpu = first(load_parts(session), Category.CPU)
    new_price = cpu.price_rub + 100
    provider = CsvPriceProvider(write_csv(tmp_path, f"brand,name,price_rub\n{cpu.brand},{cpu.name},{new_price}\n"))

    dry = update_prices(session, provider, dry_run=True)
    session.expire_all()
    assert dry.changed == 1
    assert session.get(Component, cpu.id).price_rub == new_price - 100

    report = update_prices(session, provider)
    session.expire_all()
    assert report.changed == 1
    assert session.get(Component, cpu.id).price_rub == new_price


def test_cli_reports_unreadable_file(tmp_path, caplog):
    with caplog.at_level(logging.ERROR, logger="app.prices"):
        assert run_once(tmp_path / "missing.csv", max_change=0.5, dry_run=True) is False
    assert "Импорт цен не выполнен" in caplog.text
