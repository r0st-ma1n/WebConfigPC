"""Тесты проверок из скрипта оценки объяснений (backend/scripts/eval_explanations.py)."""

from scripts.eval_explanations import check

FACTS = {
    "warnings": [],
    "over_budget_rub": 0,
    "price_rub": 128_100,
    "budget_rub": 130_000,
    "ram": {"type": "DDR5", "capacity_gb": 32},
    "upgrades": [{"text": "Ryzen 7 7800X3D вместо Ryzen 5 7500F: +20 200 ₽", "worth_it": False}],
    "savings": [
        {"text": "1 ТБ вместо 2 ТБ: экономия 4 000 ₽", "worth_it": True},
        {"text": "Zalman T6 вместо DeepCool CC560: экономия 2 500 ₽", "worth_it": True},
    ],
}


def test_correct_text_passes():
    text = (
        "Сборка за 128 100 ₽ укладывается в бюджет 130 тысяч. Память 32 ГБ DDR5. "
        "Процессор за почти 20 000 ₽ не стоит своих денег. "
        "Сэкономить можно на накопителе и корпусе — всего 6 500 ₽."
    )  # округление и сумма — не ошибки
    assert check(text, FACTS) == []


def test_invented_facts_are_found():
    text = "Есть предупреждение о корпусе. Сборка немного дороже бюджета. Память DDR4 на 48 ГБ, см. upgrades."
    assert check(text, FACTS) == [
        "выдуманное предупреждение",
        "«дороже бюджета», хотя сборка в бюджете",
        "числа 48 нет в данных",
        "служебное слово «upgrades»",
        "DDR4 вместо DDR5",
    ]


def test_invented_saving_only_when_there_is_none():
    no_savings = {**FACTS, "savings": []}
    assert check("Можно сэкономить 1 000 рублей.", no_savings) == ["выдуманная экономия", "числа 1000 нет в данных"]
    assert check("Сэкономить здесь не получится.", no_savings) == []
    assert check("Экономия в этой сборке отсутствует.", no_savings) == []
