"""Поиск сборок: ядро рекомендательной системы.

Алгоритм для каждого варианта (дешевле / оптимальная / с запасом):

1. Перебираются все пары (процессор, видеокарта) с учётом предпочтений.
   Каталог небольшой (~20 × 20 позиций), поэтому полный перебор пар быстрый
   и даёт точный, а не приблизительный результат.
2. Каждая пара достраивается до полной сборки: плата → память → накопитель →
   кулер → корпус → блок питания. В каждой категории берётся лучшая совместимая
   деталь, которая укладывается в свою долю бюджета (см. budget.py), а если такой
   нет, то самая дешёвая совместимая.
3. Сборка проверяется модулем совместимости и требованиями сценария.
4. Лучшие сборки «докупаются»: оставшиеся деньги тратятся на улучшения с лучшим
   соотношением прироста оценки к доплате, но только если прирост заметный.
   Так деньги не уходят на то, что почти не влияет на результат.
5. Выбирается сборка с наибольшей оценкой. Если несколько сборок отличаются
   по оценке меньше чем на 1%, берётся самая дешёвая.
"""
from collections import defaultdict
from collections.abc import Callable

from app.compatibility import check_build, recommended_psu_w
from app.domain import Build
from app.models import Category, Component, Cooler, Cpu, Gpu, Psu, Storage
from app.recommender.budget import allocate_budget
from app.recommender.params import (
    MIN_VRAM_GB, TIER_BUDGET_FACTOR, RecommendError, RecommendRequest, Scenario, Tier,
)
from app.recommender.scoring import future_proof_bonus, score

C = Category

# Сколько лучших сборок после шага 2 «докупать» на шаге 4
TOP_CANDIDATES = 12
# Улучшение принимается, если оно даёт хотя бы 30% от средней «оценки за рубль» сборки
MIN_UPGRADE_EFFICIENCY = 0.3
# Сборки, отличающиеся по оценке меньше чем на 1%, считаются равными
SCORE_TIE = 0.01
# Следующий вариант показывается, только если он лучше предыдущего хотя бы на 2%
MIN_TIER_GAIN = 0.02
# Категории, которые можно улучшать на шаге 4 (CPU и GPU уже перебраны полностью)
UPGRADE_CATEGORIES = [C.RAM, C.STORAGE, C.MOTHERBOARD, C.COOLER, C.CASE, C.PSU]
# Предупреждения совместимости, с которыми система сборку не рекомендует
# (в ручном режиме пользователь может их принять, а рекомендация должна быть чистой)
AVOIDED_WARNINGS = {"cooler_weak", "psu_low_headroom", "board_vrm"}
# Порядок исправления зависимых деталей после замены (см. repair)
REPAIR_ORDER = [C.MOTHERBOARD, C.RAM, C.STORAGE, C.COOLER, C.CASE, C.PSU]


class Catalog:
    """Каталог комплектующих, разложенный по категориям."""

    def __init__(self, parts: list[Component]):
        self.by_id = {p.id: p for p in parts}
        self._by_category: dict[Category, list[Component]] = defaultdict(list)
        for p in parts:
            self._by_category[p.category].append(p)

    def of(self, category: Category) -> list[Component]:
        return self._by_category[category]


def pick(options: list[Component], limit: int | None,
         value: Callable[[Component], float]) -> Component | None:
    """Выбор детали из совместимых вариантов.

    Берётся деталь с наибольшей пользой (value) среди тех, что укладываются в limit рублей;
    при равной пользе — более дешёвая. Если в limit не укладывается ничего (или limit=None),
    берётся самая дешёвая.
    """
    if not options:
        return None
    if limit is not None:
        affordable = [o for o in options if o.price_rub <= limit]
        if affordable:
            return max(affordable, key=lambda o: (round(value(o), 2), -o.price_rub))
    return min(options, key=lambda o: (o.price_rub, -value(o)))


class BuildSearch:
    def __init__(self, catalog: Catalog, request: RecommendRequest):
        self.catalog = catalog
        self.request = request
        self._options_cache: dict[tuple, list[Component]] = {}

    # ---------- Оценка и требования ----------

    def score(self, build: Build) -> float:
        return score(build, self.request)

    def tier_value(self, build: Build, tier: Tier) -> float:
        """Значение, по которому выбирается лучшая сборка варианта."""
        value = self.score(build)
        if tier == Tier.HEADROOM:
            value += future_proof_bonus(build)
        return value

    def needs_gpu(self) -> bool:
        return self.request.scenario != Scenario.OFFICE or self.request.gpu_id is not None

    def storage_ok(self, s: Storage) -> bool:
        """Системный накопитель — только SSD достаточного объёма."""
        return s.kind != "HDD" and s.capacity_gb >= self.request.min_storage_gb

    @staticmethod
    def psu_ok(psu: Psu) -> bool:
        """Блоки питания без сертификата 80 PLUS система не рекомендует:
        у них часто занижена реальная мощность и нет нормальных защит."""
        return psu.efficiency.startswith("80+")

    def is_valid(self, build: Build) -> bool:
        """Сборка совместима и отвечает требованиям сценария."""
        # Баланс CPU/GPU здесь не проверяется: он учитывается в оценке сборки
        result = check_build(build, complete=True, balance_resolution=None)
        if not result.is_compatible or any(w.code in AVOIDED_WARNINGS for w in result.warnings):
            return False
        if self.needs_gpu() and build.gpu is None:
            return False
        if build.gpu and build.gpu.vram_gb < MIN_VRAM_GB and self.request.gpu_id is None:
            return False
        if build.ram.capacity_gb < self.request.min_ram_gb:
            return False
        return self.psu_ok(build.psu) and any(self.storage_ok(s) for s in build.storages)

    # ---------- Варианты процессора и видеокарты ----------

    def cpu_options(self) -> list[Cpu]:
        req = self.request
        cpus = self.catalog.of(C.CPU)
        if req.cpu_id is not None:
            cpus = [c for c in cpus if c.id == req.cpu_id]
            if not cpus:
                raise RecommendError("Выбранный процессор не найден в каталоге.")
            return cpus
        if req.platform:
            cpus = [c for c in cpus if c.brand.lower() == req.platform.value]
        if not self.needs_gpu():
            # Без видеокарты нужен процессор со встроенной графикой
            cpus = [c for c in cpus if c.has_igpu]
        return cpus

    def gpu_options(self) -> list[Gpu | None]:
        req = self.request
        if req.gpu_id is not None:
            gpus = [g for g in self.catalog.of(C.GPU) if g.id == req.gpu_id]
            if not gpus:
                raise RecommendError("Выбранная видеокарта не найдена в каталоге.")
            return gpus
        if not self.needs_gpu():
            return [None]
        return self.catalog.of(C.GPU)

    # ---------- Достройка сборки ----------

    def _options(self, category: Category, context: Build,
                 extra: Callable[[Component], bool] = lambda _: True) -> list[Component]:
        """Детали категории, совместимые с context. Результат кэшируется:
        например, платы для одного процессора ищутся один раз, а не для каждой видеокарты."""
        key = (category, tuple(context.part_ids))
        if key not in self._options_cache:
            self._options_cache[key] = [
                c for c in self.catalog.of(category)
                if extra(c) and not check_build(context.with_part(c), balance_resolution=None).errors
            ]
        return self._options_cache[key]

    def complete(self, cpu: Cpu, gpu: Gpu | None, allocation: dict[Category, int] | None) -> Build | None:
        """Достраивает пару (CPU, GPU) до полной сборки.

        allocation — доли бюджета по категориям; None — собрать максимально дешёво.
        Польза детали — насколько она поднимает оценку сборки в сценарии пользователя.
        Например, 64 ГБ памяти в играх не полезнее 32 ГБ, поэтому возьмутся 32 ГБ.
        """
        build = Build(cpu=cpu, gpu=gpu)

        def choose(category: Category, options: list[Component]) -> Component | None:
            limit = allocation[category] if allocation else None
            return pick(options, limit, lambda part: self.score(build.replace_part(part)))

        board = choose(C.MOTHERBOARD, self._options(C.MOTHERBOARD, Build(cpu=cpu)))
        if board is None:
            return None
        build = build.with_part(board)

        min_ram = self.request.min_ram_gb
        ram = choose(C.RAM, self._options(C.RAM, Build(cpu=cpu, motherboard=board),
                                          lambda r: r.capacity_gb >= min_ram))
        storage = choose(C.STORAGE, self._options(C.STORAGE, Build(motherboard=board), self.storage_ok))
        if ram is None or storage is None:
            return None
        build = build.with_part(ram).with_part(storage)

        if not cpu.includes_cooler:
            cooler = choose(C.COOLER, self._options(C.COOLER, Build(cpu=cpu),
                                                    lambda c: c.max_tdp_w >= cpu.power_w))
            if cooler is None:
                return None
            build = build.with_part(cooler)

        case = choose(C.CASE, self._options(C.CASE, Build(motherboard=board, gpu=gpu, cooler=build.cooler)))
        if case is None:
            return None
        build = build.with_part(case)

        need_w = recommended_psu_w(build)
        psu = choose(C.PSU, [p for p in self.catalog.of(C.PSU) if p.wattage >= need_w and self.psu_ok(p)])
        if psu is None:
            return None
        build = build.with_part(psu)
        return build if self.is_valid(build) else None

    def improve(self, build: Build, limit: int) -> Build:
        """Тратит оставшиеся деньги на самые выгодные улучшения (шаг 4)."""
        current_score = self.score(build)
        while True:
            best: Build | None = None
            # Улучшение должно быть не хуже 30% от средней «оценки за рубль» всей сборки
            best_eff = MIN_UPGRADE_EFFICIENCY * current_score / build.total_price
            for category in UPGRADE_CATEGORIES:
                current = build.part_in_slot(category)
                for candidate in self.catalog.of(category):
                    if current and candidate.id == current.id:
                        continue
                    extra = candidate.price_rub - (current.price_rub if current else 0)
                    if build.total_price + extra > limit:
                        continue
                    new = build.replace_part(candidate)
                    gain = self.score(new) - current_score
                    if gain <= 0:
                        continue
                    efficiency = gain / max(extra, 1)
                    if efficiency > best_eff and self.is_valid(new):
                        best, best_eff = new, efficiency
            if best is None:
                return build
            build, current_score = best, self.score(best)

    def repair(self, build: Build, keep: Component) -> Build | None:
        """Делает сборку снова корректной после замены детали keep.

        Например, при замене процессора AMD на Intel нужна другая плата, а к ней,
        возможно, другая память. Детали, которые перестали подходить, заменяются
        на самые дешёвые подходящие; остальные не трогаются.
        """
        if self.is_valid(build):
            return build
        for category in REPAIR_ORDER:
            if category == keep.category or self._slot_ok(build, category):
                continue
            options = [c for c in self.catalog.of(category) if self._slot_ok(build.replace_part(c), category)]
            if not options:
                return None
            build = build.replace_part(min(options, key=lambda c: c.price_rub))
        return build if self.is_valid(build) else None

    def _slot_ok(self, build: Build, category: Category) -> bool:
        """Деталь в слоте не участвует в ошибках и отвечает требованиям сценария."""
        part = build.part_in_slot(category)
        if part is None:
            # Пустым может быть только слот кулера, и только при боксовом кулере
            return category == C.COOLER and build.cpu is not None and build.cpu.includes_cooler
        result = check_build(build, balance_resolution=None)
        bad = result.errors + [w for w in result.warnings if w.code in AVOIDED_WARNINGS]
        if any(part.id in issue.part_ids for issue in bad):
            return False
        match category:
            case C.RAM:
                return part.capacity_gb >= self.request.min_ram_gb
            case C.STORAGE:
                return self.storage_ok(part)
            case C.PSU:
                return part.wattage >= recommended_psu_w(build) and self.psu_ok(part)
        return True

    # ---------- Поиск вариантов ----------

    def search(self) -> dict[Tier, Build]:
        budget = self.request.budget
        minimal = [
            b for cpu in self.cpu_options() for gpu in self.gpu_options()
            if (b := self.complete(cpu, gpu, None)) is not None
        ]
        if not minimal:
            raise RecommendError("Не удалось собрать совместимую сборку с такими условиями.")
        cheapest = min(b.total_price for b in minimal)
        if cheapest > budget:
            raise RecommendError(
                f"Бюджета не хватает: самая дешёвая подходящая сборка стоит {format_rub(cheapest)}."
            )

        results: dict[Tier, Build] = {}
        for tier in Tier:
            limit = round(budget * TIER_BUDGET_FACTOR[tier])
            allocation = allocate_budget(limit, self.request.scenario, self.request.resolution)
            # Победители предыдущих (более дешёвых) вариантов тоже участвуют:
            # так более дорогой вариант гарантированно не хуже более дешёвого
            candidates = list(results.values())
            for b_min in minimal:
                if b_min.total_price > limit:
                    continue
                b = self.complete(b_min.cpu, b_min.gpu, allocation)
                candidates.append(b if b is not None and b.total_price <= limit else b_min)
            if not candidates:
                continue  # например, на «дешевле» (80% бюджета) собрать ничего нельзя
            candidates.sort(key=self.score, reverse=True)
            improved = [self.improve(b, limit) for b in candidates[:TOP_CANDIDATES]]
            results[tier] = self.choose(improved, tier)
        return self.drop_similar(results)

    def drop_similar(self, results: dict[Tier, Build]) -> dict[Tier, Build]:
        """Оставляет только варианты, которые заметно лучше предыдущего.

        Если «Оптимальная» почти не лучше «Дешевле», то дешёвая сборка и есть
        оптимальная: показывается она одна. Если «С запасом» почти не лучше
        оптимальной, она не показывается.
        """
        final: dict[Tier, Build] = {}
        for tier, build in results.items():
            if final:
                last_tier, last = list(final.items())[-1]
                if self.tier_value(build, tier) < self.tier_value(last, tier) * (1 + MIN_TIER_GAIN):
                    if tier == Tier.OPTIMAL:
                        del final[last_tier]
                        final[tier] = last
                    continue
            final[tier] = build
        return final

    def choose(self, builds: list[Build], tier: Tier) -> Build:
        best = max(self.tier_value(b, tier) for b in builds)
        near_best = [b for b in builds if self.tier_value(b, tier) >= best * (1 - SCORE_TIE)]
        return min(near_best, key=lambda b: b.total_price)


def format_rub(value: int) -> str:
    """12345 -> '12 345 ₽' (неразрывный пробел между разрядами)."""
    return f"{value:,}".replace(",", " ") + " ₽"
