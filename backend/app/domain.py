"""Сборка ПК как простой объект предметной области.

Сборка ничего не знает о базе данных: она хранит уже загруженные детали.
Поэтому модули совместимости и подбора можно тестировать без PostgreSQL.
"""
from dataclasses import dataclass, field
from functools import cached_property

from app.models import Case, Category, Component, Cooler, Cpu, Gpu, Motherboard, Psu, Ram, Storage

# Имя атрибута сборки для каждой категории (накопители хранятся списком)
SLOT_BY_CATEGORY: dict[Category, str] = {
    Category.CPU: "cpu",
    Category.GPU: "gpu",
    Category.MOTHERBOARD: "motherboard",
    Category.RAM: "ram",
    Category.STORAGE: "storages",
    Category.PSU: "psu",
    Category.CASE: "case",
    Category.COOLER: "cooler",
}


@dataclass(frozen=True)
class Build:
    """Сборка неизменяема: замена детали возвращает новую сборку. Поэтому производные
    значения (ключ, цена, потребление) считаются один раз — при переборе вариантов
    они запрашиваются у одной и той же сборки много раз."""

    cpu: Cpu | None = None
    gpu: Gpu | None = None
    motherboard: Motherboard | None = None
    ram: Ram | None = None
    storages: list[Storage] = field(default_factory=list)
    psu: Psu | None = None
    case: Case | None = None
    cooler: Cooler | None = None

    @classmethod
    def from_parts(cls, parts: list[Component]) -> Build:
        """Раскладывает список деталей по слотам сборки."""
        build = cls()
        for part in parts:
            build = build.with_part(part)
        return build

    def with_part(self, part: Component) -> Build:
        """Новая сборка, в которой деталь поставлена в свой слот.

        Исходная сборка не меняется: это удобно при переборе вариантов.
        Накопитель добавляется к уже выбранным, остальные детали заменяют прежние.
        """
        if isinstance(part, Storage):
            return self._copy(storages=[*self.storages, part])
        return self._copy(**{SLOT_BY_CATEGORY[part.category]: part})

    def replace_part(self, part: Component) -> Build:
        """Как with_part, но накопитель заменяет все прежние (сборки из подбора
        содержат один накопитель). Используется при поиске замен."""
        if isinstance(part, Storage):
            return self._copy(storages=[part])
        return self.with_part(part)

    def _copy(self, **changes: object) -> Build:
        # Прямой вызов конструктора: dataclasses.replace в переборе заметно медленнее
        slots = {"cpu": self.cpu, "gpu": self.gpu, "motherboard": self.motherboard, "ram": self.ram,
                 "storages": self.storages, "psu": self.psu, "case": self.case, "cooler": self.cooler}
        return Build(**(slots | changes))  # type: ignore[arg-type]

    def part_in_slot(self, category: Category) -> Component | None:
        slot = SLOT_BY_CATEGORY[category]
        if slot == "storages":
            return self.storages[0] if self.storages else None
        return getattr(self, slot)

    @cached_property
    def key(self) -> tuple[int, ...]:
        """Состав сборки как ключ словаря. id уникальны во всём каталоге, поэтому
        по набору id однозначно восстанавливается, какая деталь в каком слоте."""
        return tuple(self.part_ids)

    @property
    def part_ids(self) -> list[int]:
        return [p.id for p in self.parts]

    @property
    def parts(self) -> list[Component]:
        single = [self.cpu, self.gpu, self.motherboard, self.ram, self.psu, self.case, self.cooler]
        return [p for p in single if p is not None] + list(self.storages)

    @cached_property
    def total_price(self) -> int:
        return sum(p.price_rub for p in self.parts)

    @cached_property
    def estimated_power_w(self) -> int:
        """Потребление сборки под нагрузкой: сумма потребления всех деталей.

        У блока питания power_w = 0, он энергию отдаёт, а не потребляет.
        """
        return sum(p.power_w for p in self.parts)
