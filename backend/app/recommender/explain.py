"""Объяснение выбора сборки.

Сначала собираются «факты» — структурированные данные о сборке и о том, почему
она получилась такой (доли бюджета, баланс CPU/GPU, запас блока питания...).
Из фактов строится шаблонное объяснение. Эти же факты передаются LLM, если она
подключена: модель только пересказывает их простым языком и ничего не выбирает сама.
"""
from app.compatibility import CheckResult
from app.domain import Build
from app.models import Category
from app.recommender.builder import format_rub
from app.recommender.params import SCENARIO_TITLES, TIER_BUDGET_FACTOR, TIER_TITLES, RecommendRequest, Scenario, Tier
from app.recommender.scoring import CURRENT_SOCKETS, ScoreBreakdown

C = Category

CATEGORY_TITLES = {
    C.CPU: "процессор", C.GPU: "видеокарта", C.MOTHERBOARD: "материнская плата", C.RAM: "память",
    C.STORAGE: "накопитель", C.PSU: "блок питания", C.CASE: "корпус", C.COOLER: "охлаждение",
}


def build_facts(request: RecommendRequest, tier: Tier | None, build: Build, breakdown: ScoreBreakdown,
                check: CheckResult, upgrades: list[dict], savings: list[dict]) -> dict:
    """Факты о сборке в виде словаря (его легко передать в LLM как JSON)."""
    price = build.total_price
    spent = {}
    for category in C:
        part = build.part_in_slot(category)
        if part is not None:
            spent[CATEGORY_TITLES[category]] = round(part.price_rub / price * 100)

    limit = round(request.budget * TIER_BUDGET_FACTOR[tier]) if tier else request.budget
    cpu, gpu, ram, psu = build.cpu, build.gpu, build.ram, build.psu
    # Неполные сборки отсекаются раньше (evaluate_build, подбор), здесь все слоты заполнены
    assert cpu is not None and ram is not None and psu is not None
    storage = build.storages[0]
    return {
        "variant": TIER_TITLES[tier] if tier else "Ваша сборка",
        "tier": tier.value if tier else None,
        "scenario": request.scenario.value,
        "scenario_title": SCENARIO_TITLES[request.scenario],
        "resolution": request.resolution.value if request.is_gaming else None,
        "budget_rub": request.budget,
        "price_rub": price,
        "unused_rub": max(limit - price, 0),
        "over_budget_rub": max(price - request.budget, 0),
        "score": round(breakdown.total, 1),
        "parts": {CATEGORY_TITLES[p.category]: p.title for p in build.parts},
        "price_share_pct": spent,
        "cpu": {"title": cpu.title, "cores": cpu.cores, "threads": cpu.threads,
                "has_igpu": cpu.has_igpu, "socket": cpu.socket,
                "current_platform": cpu.socket in CURRENT_SOCKETS},
        "gpu": {"title": gpu.title, "vram_gb": gpu.vram_gb,
                "nvidia": gpu.chip.startswith(("RTX", "GTX"))} if gpu else None,
        # Что ограничивает FPS в играх: "cpu", "gpu" или None (пара сбалансирована)
        "gaming_limiter": breakdown.limiter,
        "ram": {"capacity_gb": ram.capacity_gb, "type": ram.memory_type,
                "modules": ram.modules, "speed_mhz": ram.speed_mhz},
        "storage": {"title": storage.title, "kind": storage.kind, "capacity_gb": storage.capacity_gb},
        "power_w": build.estimated_power_w,
        "psu": {"title": psu.title, "wattage": psu.wattage, "efficiency": psu.efficiency,
                "headroom_pct": round((psu.wattage / build.estimated_power_w - 1) * 100)},
        "warnings": [w.message for w in check.warnings],
        "upgrades": upgrades,
        "savings": savings,
    }



def plural(n: int, forms: tuple[str, str, str]) -> str:
    """plural(5, ("ядро", "ядра", "ядер")) -> "5 ядер"."""
    if n % 10 == 1 and n % 100 != 11:
        form = forms[0]
    elif 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        form = forms[1]
    else:
        form = forms[2]
    return f"{n} {form}"


def template_explanation(f: dict) -> str:
    """Объяснение по шаблону: используется без LLM и как запасной вариант."""
    paragraphs = []
    scenario = Scenario(f["scenario"])
    cpu, gpu, ram, storage, psu = f["cpu"], f["gpu"], f["ram"], f["storage"], f["psu"]

    head = f"Вариант «{f['variant']}» — сборка для сценария «{f['scenario_title']}»"
    if f["tier"] is None:
        head = f"Ваша сборка для сценария «{f['scenario_title']}»"
    if f["resolution"]:
        head += f" в разрешении {f['resolution']}"
    paragraphs.append(f"{head}: {format_rub(f['price_rub'])} при бюджете {format_rub(f['budget_rub'])}.")

    # Главное вложение и баланс
    if scenario == Scenario.GAMING:
        res = f["resolution"]
        text = (f"Больше всего денег ({f['price_share_pct']['видеокарта']}% стоимости) вложено "
                f"в видеокарту {gpu['title']}: в играх именно она определяет количество кадров.")
        limiter = f["gaming_limiter"]
        if limiter is None:
            text += f" Процессор {cpu['title']} подобран ей под стать: в {res} ни одна деталь не тормозит другую."
        elif limiter == "gpu":
            text += (f" Процессор {cpu['title']} справляется с ней с запасом, поэтому в {res} упор будет "
                     f"в видеокарту — так и должно быть, деньги на процессор не переплачены.")
        else:
            text += (f" Процессор {cpu['title']} немного ограничивает её в {res}, но более мощный "
                     f"процессор при этой видеокарте не уложился бы в бюджет с лучшим результатом.")
        paragraphs.append(text)
    elif scenario == Scenario.WORKSTATION:
        text = (f"Главный упор — на процессор {cpu['title']} ({plural(cpu['cores'], ('ядро', 'ядра', 'ядер'))}, "
                f"{plural(cpu['threads'], ('поток', 'потока', 'потоков'))}): "
                f"рендер и кодирование видео используют все ядра. Видеокарта {gpu['title']} "
                f"с {gpu['vram_gb']} ГБ памяти ускоряет GPU-рендер и монтаж")
        text += (" (технологии NVIDIA CUDA и OptiX поддерживаются Blender и DaVinci Resolve)."
                 if gpu["nvidia"] else ".")
        paragraphs.append(text)
    else:
        text = f"Процессор {cpu['title']} отвечает за отзывчивость системы"
        if gpu is None:
            text += (", а его встроенной графики хватает для офиса, учёбы и видео: "
                     "отдельная видеокарта не нужна, и эти деньги остаются у вас.")
        else:
            text += "."
        paragraphs.append(text)

    # Память и накопитель
    gb = ram["capacity_gb"]
    ram_text = f"{gb} ГБ памяти {ram['type']}"
    if scenario == Scenario.GAMING:
        ram_text += (" — с запасом для современных игр вместе с браузером и Discord"
                     if gb >= 32 else " — достаточно для большинства игр")
    elif scenario == Scenario.WORKSTATION:
        ram_text += " — для монтажа и 3D объём памяти критичен: проекты и кэш хранятся в ОЗУ"
    else:
        ram_text += " — хватит для браузера с десятками вкладок и офисных программ"
    if ram["modules"] == 1:
        ram_text += " (один модуль работает в одноканальном режиме — позже стоит добавить второй)"
    storage_kind = {"NVMe": "быстрый NVMe SSD", "SATA_SSD": "SATA SSD", "HDD": "жёсткий диск"}[storage["kind"]]
    capacity = (f"{storage['capacity_gb'] // 1000} ТБ" if storage["capacity_gb"] >= 1000
                else f"{storage['capacity_gb']} ГБ")
    paragraphs.append(f"{ram_text}. Накопитель {storage['title']} — {storage_kind} на {capacity}.")

    # Питание
    paragraphs.append(
        f"Расчётное потребление — около {f['power_w']} Вт, блок питания {psu['title']} "
        f"({psu['efficiency']}) даёт запас {psu['headroom_pct']}%."
    )

    # Особенности варианта
    tier = f["tier"]
    if tier == Tier.CHEAPER:
        paragraphs.append("Это самый экономный вариант: ключевые детали сохранены, "
                          "а на второстепенных сэкономлено.")
    elif tier == Tier.HEADROOM:
        reasons = []
        if cpu["current_platform"]:
            reasons.append(f"платформа {cpu['socket']} актуальна — процессор можно будет заменить без смены платы")
        if psu["headroom_pct"] >= 50:
            reasons.append("блок питания потянет более мощную видеокарту")
        text = "Вариант с заделом на будущее"
        if f["over_budget_rub"]:
            text += f" — дороже бюджета на {format_rub(f['over_budget_rub'])}"
        text += (": " + "; ".join(reasons) + ".") if reasons else "."
        paragraphs.append(text)
    if tier == Tier.OPTIMAL and f["unused_rub"] > f["budget_rub"] * 0.03:
        paragraphs.append(f"Оставшиеся {format_rub(f['unused_rub'])} система сознательно не тратит: "
                          f"доступные улучшения дали бы слишком маленький прирост за эти деньги.")

    if f["upgrades"]:
        best = f["upgrades"][0]
        if best["worth_it"]:
            paragraphs.append(f"Если готовы доплатить, выгоднее всего: {best['text']}.")
        else:
            paragraphs.append("Доплата за отдельные детали уже почти не даёт прироста. "
                              f"Самый заметный вариант: {best['text']}.")
    if f["savings"]:
        paragraphs.append(f"Сэкономить можно так: {f['savings'][0]['text']}.")
    return "\n\n".join(paragraphs)
