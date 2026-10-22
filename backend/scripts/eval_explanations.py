"""Оценка точности объяснений сборок, которые пишет LLM.

Генерирует объяснения для нескольких типовых сборок через провайдер из .env и ищет
в тексте типичные ошибки маленьких моделей:
- выдуманное предупреждение (в данных предупреждений нет);
- выдуманная экономия (вариантов экономии нет);
- «дороже бюджета», хотя сборка в бюджете;
- числа, которых нет в данных (с допуском на округление и суммы вариантов);
- служебные слова из JSON в тексте (upgrades, worth_it...);
- не тот тип памяти (DDR4/DDR5).

Проверки ловят не всё (например, неверную оценку доплаты), поэтому тексты стоит
сохранить через --out и просмотреть. Запуск из корня проекта:

    uv run python backend/scripts/eval_explanations.py --runs 3 --out eval.json
    uv run python backend/scripts/eval_explanations.py --rescore eval.json   # перепроверить без генерации

Базу данных и бэкенд запускать не нужно: сборки подбираются по каталогу из components.json.
"""

import argparse
import json
import re
import sys
import time
from itertools import combinations
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # папка backend

from app.ai.factory import get_provider
from app.ai.service import EXPLAIN_SYSTEM, _explain_prompt
from app.balance import Resolution
from app.recommender import recommend
from app.recommender.params import RecommendRequest, Scenario, Tier
from app.seed import load_catalog

# Сборки для оценки: все варианты игровой и оптимальные для офиса и работы
REQUESTS = [
    (RecommendRequest(budget=130_000, scenario=Scenario.GAMING, resolution=Resolution.QHD), None),
    (RecommendRequest(budget=45_000, scenario=Scenario.OFFICE), Tier.OPTIMAL),
    (RecommendRequest(budget=150_000, scenario=Scenario.WORKSTATION), Tier.OPTIMAL),
]

# Числа, которые можно назвать, не беря из данных: размеры экрана, «80+», счёт до десяти
ALLOWED_NUMBERS = {1920, 1080, 2560, 1440, 3840, 2160, 80} | set(range(11))
ROUNDING = 0.03  # «почти 20 000» при 20 200 ₽ — не ошибка

SERVICE_WORDS = re.compile(
    r"\b(upgrades?|savings?|warnings?|worth_it|gaming_limiter|headroom\w*|price_share\w*|"
    r"capacity_gb|vram_gb|has_igpu|current_platform|tier|json)\b",
    re.I,
)
INVENTED_SAVING_NEGATION = re.compile(
    r"(нет|не\w*)[^.]{0,40}(сэконом|экономи)|(сэконом|экономи)\w*[^.]{0,30}(нет|не получится|нельзя|отсутству)"
)


def numbers_in_text(text: str) -> set[int]:
    """Числа из текста: «130 000» (с любым пробелом между разрядами) — одно число."""
    text = re.sub(r"(?<=\d)[\s  ](?=\d{3}\b)", "", text)
    return {int(n) for n in re.findall(r"\d+", text)}


def numbers_in(obj) -> set[int]:
    """Все числа из фактов, включая числа внутри строк («+4 000 ₽», «650W»)."""
    if isinstance(obj, dict):
        return set().union(*map(numbers_in, obj.values()))
    if isinstance(obj, list):
        return set().union(*map(numbers_in, obj))
    if isinstance(obj, bool) or obj is None:
        return set()
    if isinstance(obj, (int, float)):
        return {round(obj)}
    return numbers_in_text(str(obj))


def known_numbers(facts: dict) -> set[int]:
    known = numbers_in(facts) | ALLOWED_NUMBERS
    # Модель может сложить суммы вариантов: «экономия на накопителе и корпусе — 6 500 ₽»
    amounts = [max(numbers_in_text(a["text"]) - {0}, default=0) for a in facts["upgrades"] + facts["savings"]]
    known |= {a + b for a, b in combinations(amounts, 2)}
    return known


def is_known(n: int, known: set[int]) -> bool:
    if n in known or n * 1000 in known:  # «130 тысяч»
        return True
    return n >= 1000 and any(abs(n - k) <= k * ROUNDING for k in known if k >= 1000)


def check(text: str, facts: dict) -> list[str]:
    """Список найденных ошибок в объяснении (пустой — ошибок не найдено)."""
    problems = []
    low = text.lower()
    if not facts["warnings"] and "предупрежд" in low:
        problems.append("выдуманное предупреждение")
    if not facts["savings"] and re.search(r"сэконом|экономи", low) and not INVENTED_SAVING_NEGATION.search(low):
        problems.append("выдуманная экономия")
    if not facts["over_budget_rub"] and re.search(r"дороже(,)? (чем )?бюджет|выше бюджета|превыша\w* бюджет", low):
        problems.append("«дороже бюджета», хотя сборка в бюджете")
    known = known_numbers(facts)
    problems += [f"числа {n} нет в данных" for n in sorted(numbers_in_text(text)) if not is_known(n, known)]
    problems += [f"служебное слово «{w}»" for w in sorted({m.group(0).lower() for m in SERVICE_WORDS.finditer(text)})]
    ram = facts["ram"]["type"]
    problems += [f"{t} вместо {ram}" for t in sorted(set(re.findall(r"DDR\d", text))) if t != ram]
    return problems


def builds() -> list[tuple[str, dict]]:
    parts = load_catalog(with_ids=True)
    out = []
    for request, only_tier in REQUESTS:
        for rec in recommend(parts, request).recommendations:
            if only_tier is None or rec.tier == only_tier:
                out.append((f"{request.scenario.value}/{rec.tier.value}", rec.facts))
    return out


def report(results: list[dict]) -> None:
    for r in results:
        print(f"{r['build']:22} #{r['run']}: {'; '.join(r['problems']) or 'ок'}")
    bad = sum(bool(r["problems"]) for r in results)
    print(f"\nТекстов с ошибками: {bad} из {len(results)}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--runs", type=int, default=2, help="генераций на каждую сборку")
    parser.add_argument("--out", type=Path, help="сохранить тексты и ошибки в JSON")
    parser.add_argument("--rescore", type=Path, help="перепроверить тексты из сохранённого JSON")
    args = parser.parse_args()

    facts_by_build = dict(builds())
    if args.rescore:
        saved = json.loads(args.rescore.read_text(encoding="utf-8"))
        report([{**r, "problems": check(r["text"], facts_by_build[r["build"]])} for r in saved])
        return

    provider = get_provider()
    if provider is None:
        sys.exit("ИИ не подключён: задайте LLM_PROVIDER и LLM_API_KEY в .env")
    print(f"Модель: {provider.name} / {provider.model}\n")

    results, start = [], time.time()
    for name, facts in facts_by_build.items():
        for run in range(args.runs):
            text = provider.generate_text(EXPLAIN_SYSTEM, _explain_prompt(facts)).strip()
            results.append({"build": name, "run": run, "problems": check(text, facts), "text": text})
            print(f"{name:22} #{run}: {'; '.join(results[-1]['problems']) or 'ок'}", flush=True)

    bad = sum(bool(r["problems"]) for r in results)
    print(f"\nТекстов с ошибками: {bad} из {len(results)}, время: {time.time() - start:.0f} с")
    if args.out:
        args.out.write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"Тексты сохранены в {args.out}")


if __name__ == "__main__":
    main()
