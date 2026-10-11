"""Сборка ПК как простой объект предметной области.

Сборка ничего не знает о базе данных: она хранит уже загруженные детали.
Поэтому модули совместимости и подбора можно тестировать без PostgreSQL.
"""
from dataclasses import dataclass, field, replace

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


@dataclass
class Build:
    cpu: Cpu | None = None
    gpu: Gpu | None = None
    motherboard: Motherboard | None = None
    ram: Ram | None = None
    storages: list[Storage] = field(default_factory=list)
    psu: Psu | None = None
    case: Case | None = None
    cooler: Cooler | None = None

    @classmethod
    def from_parts(cls, parts: list[Component]) -> "Build":
        """Раскладывает список деталей по слотам сборки."""
        build = cls()
        for part in parts:
            build = build.with_part(part)
        return build

    def with_part(self, part: Component) -> "Build":
        """Новая сборка, в которой деталь поставлена в свой слот.

        Исходная сборка не меняется: это удобно при переборе вариантов.
        Накопитель добавляется к уже выбранным, остальные детали заменяют прежние.
        """
        slot = SLOT_BY_CATEGORY[part.category]
        if slot == "storages":
            return replace(self, storages=[*self.storages, part])
        return replace(self, **{slot: part})

    @property
    def parts(self) -> list[Component]:
        single = [self.cpu, self.gpu, self.motherboard, self.ram, self.psu, self.case, self.cooler]
        return [p for p in single if p is not None] + list(self.storages)

    @property
    def total_price(self) -> int:
        return sum(p.price_rub for p in self.parts)

    @property
    def estimated_power_w(self) -> int:
        """Потребление сборки под нагрузкой: сумма потребления всех деталей.

        У блока питания power_w = 0, он энергию отдаёт, а не потребляет.
        """
        return sum(p.power_w for p in self.parts)
