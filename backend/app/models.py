"""ORM-модели комплектующих.

Используется наследование с объединением таблиц (joined table inheritance):
- общие поля всех деталей (цена, оценка производительности, потребление) лежат в таблице components;
- характеристики конкретной категории лежат в своей таблице (cpus, gpus, ...),
  строка которой связана с components по тому же id (связь 1:1).

SQLAlchemy сам делает JOIN и по полю category понимает, объект какого класса создать.
Объекты этих классов можно создавать и без базы данных: так делают тесты.
"""
import enum
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class Category(enum.StrEnum):
    CPU = "cpu"
    GPU = "gpu"
    MOTHERBOARD = "motherboard"
    RAM = "ram"
    STORAGE = "storage"
    PSU = "psu"
    CASE = "case"
    COOLER = "cooler"


class Component(Base):
    """Общая часть любой комплектующей."""

    __tablename__ = "components"

    id: Mapped[int] = mapped_column(primary_key=True)
    # native_enum=False: в БД это обычный VARCHAR с проверкой значений, так проще мигрировать
    category: Mapped[Category] = mapped_column(
        Enum(Category, native_enum=False, length=20, values_callable=lambda e: [m.value for m in e]),
        index=True,
    )
    brand: Mapped[str] = mapped_column(String(50))
    name: Mapped[str] = mapped_column(String(150))
    price_rub: Mapped[int]
    # Оценка производительности 0–100 внутри своей категории.
    # Для CPU это игровая производительность, многопоточная лежит отдельно в Cpu.multicore_score
    perf_score: Mapped[int]
    # Потребление под нагрузкой, Вт. Нужно для расчёта блока питания
    power_w: Mapped[int] = mapped_column(default=0)
    price_updated_at: Mapped[datetime] = mapped_column(server_default=func.now())

    # with_polymorphic="*": при запросе к Component сразу делается JOIN со всеми
    # дочерними таблицами. Иначе характеристики подгружались бы отдельными запросами
    # и были бы недоступны после закрытия сессии. Каталог маленький, так что это дёшево.
    __mapper_args__ = {"polymorphic_on": "category", "with_polymorphic": "*"}

    @property
    def title(self) -> str:
        return f"{self.brand} {self.name}"

    def __repr__(self) -> str:
        return f"<{type(self).__name__} {self.id}: {self.title}, {self.price_rub} ₽>"


def _child_id() -> Mapped[int]:
    """Первичный ключ дочерней таблицы, он же внешний ключ на components.id."""
    return mapped_column(ForeignKey("components.id", ondelete="CASCADE"), primary_key=True)


class Cpu(Component):
    __tablename__ = "cpus"
    __mapper_args__ = {"polymorphic_identity": Category.CPU}

    id: Mapped[int] = _child_id()
    socket: Mapped[str] = mapped_column(String(20))
    cores: Mapped[int]
    threads: Mapped[int]
    base_ghz: Mapped[float]
    boost_ghz: Mapped[float]
    # Какие типы памяти поддерживает контроллер процессора (у Intel LGA1700 оба)
    memory_types: Mapped[list[str]] = mapped_column(ARRAY(String(10)))
    has_igpu: Mapped[bool]
    includes_cooler: Mapped[bool]
    # Производительность в многопоточных задачах (рендер, видео), 0–100
    multicore_score: Mapped[int]


class Gpu(Component):
    __tablename__ = "gpus"
    __mapper_args__ = {"polymorphic_identity": Category.GPU}

    id: Mapped[int] = _child_id()
    chip: Mapped[str] = mapped_column(String(50))
    vram_gb: Mapped[int]
    length_mm: Mapped[int]
    recommended_psu_w: Mapped[int]


class Motherboard(Component):
    __tablename__ = "motherboards"
    __mapper_args__ = {"polymorphic_identity": Category.MOTHERBOARD}

    id: Mapped[int] = _child_id()
    socket: Mapped[str] = mapped_column(String(20))
    chipset: Mapped[str] = mapped_column(String(20))
    form_factor: Mapped[str] = mapped_column(String(10))  # ATX / mATX / ITX
    memory_type: Mapped[str] = mapped_column(String(10))  # DDR4 / DDR5
    memory_slots: Mapped[int]
    max_memory_gb: Mapped[int]
    m2_slots: Mapped[int]


class Ram(Component):
    __tablename__ = "rams"
    __mapper_args__ = {"polymorphic_identity": Category.RAM}

    id: Mapped[int] = _child_id()
    memory_type: Mapped[str] = mapped_column(String(10))
    capacity_gb: Mapped[int]  # объём всего комплекта
    modules: Mapped[int]  # сколько планок в комплекте
    speed_mhz: Mapped[int]


class Storage(Component):
    __tablename__ = "storages"
    __mapper_args__ = {"polymorphic_identity": Category.STORAGE}

    id: Mapped[int] = _child_id()
    kind: Mapped[str] = mapped_column(String(10))  # NVMe / SATA_SSD / HDD
    interface: Mapped[str] = mapped_column(String(10))  # M.2 / SATA
    capacity_gb: Mapped[int]


class Psu(Component):
    __tablename__ = "psus"
    __mapper_args__ = {"polymorphic_identity": Category.PSU}

    id: Mapped[int] = _child_id()
    wattage: Mapped[int]
    efficiency: Mapped[str] = mapped_column(String(20))  # 80+ Bronze / Gold / ...


class Case(Component):
    __tablename__ = "cases"
    __mapper_args__ = {"polymorphic_identity": Category.CASE}

    id: Mapped[int] = _child_id()
    supported_form_factors: Mapped[list[str]] = mapped_column(ARRAY(String(10)))
    max_gpu_length_mm: Mapped[int]
    max_cooler_height_mm: Mapped[int]
    # Максимальный размер радиатора СЖО (0 — СЖО не ставится)
    max_radiator_mm: Mapped[int]


class Cooler(Component):
    __tablename__ = "coolers"
    __mapper_args__ = {"polymorphic_identity": Category.COOLER}

    id: Mapped[int] = _child_id()
    kind: Mapped[str] = mapped_column(String(10))  # air / aio
    height_mm: Mapped[int]  # для СЖО 0: высоту ограничивает радиатор, а не башня
    radiator_mm: Mapped[int]  # для воздушного 0
    sockets: Mapped[list[str]] = mapped_column(ARRAY(String(20)))
    max_tdp_w: Mapped[int]


# Соответствие категории и класса: удобно в сидере, API и ручном режиме
MODEL_BY_CATEGORY: dict[Category, type[Component]] = {
    Category.CPU: Cpu,
    Category.GPU: Gpu,
    Category.MOTHERBOARD: Motherboard,
    Category.RAM: Ram,
    Category.STORAGE: Storage,
    Category.PSU: Psu,
    Category.CASE: Case,
    Category.COOLER: Cooler,
}


# ---------- Сохранённые сборки ----------


class SavedBuild(Base):
    """Сборка, сохранённая пользователем, чтобы поделиться ссылкой /b/<slug>."""

    __tablename__ = "saved_builds"

    id: Mapped[int] = mapped_column(primary_key=True)
    # Короткий случайный код для ссылки: по нему нельзя перебрать чужие сборки, как по id
    slug: Mapped[str] = mapped_column(String(16), unique=True)
    # Параметры подбора (бюджет, сценарий...): по ним сборка оценивается при открытии ссылки
    params: Mapped[dict] = mapped_column(JSONB)
    tier: Mapped[str | None] = mapped_column(String(20))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    parts: Mapped[list[SavedBuildPart]] = relationship(
        back_populates="build", cascade="all, delete-orphan", lazy="selectin", order_by="SavedBuildPart.position"
    )


class SavedBuildPart(Base):
    """Деталь сохранённой сборки и её цена на момент сохранения.

    Цены в каталоге меняются, а по сохранённой цене видно, насколько сборка подорожала."""

    __tablename__ = "saved_build_parts"

    build_id: Mapped[int] = mapped_column(ForeignKey("saved_builds.id", ondelete="CASCADE"), primary_key=True)
    # Порядковый номер детали в сборке. Ключ не (build_id, component_id): в сборке
    # может быть два одинаковых накопителя
    position: Mapped[int] = mapped_column(primary_key=True)
    # RESTRICT: деталь из каталога нельзя удалить, пока на неё ссылается сохранённая сборка
    component_id: Mapped[int] = mapped_column(ForeignKey("components.id", ondelete="RESTRICT"), index=True)
    price_rub: Mapped[int]

    build: Mapped[SavedBuild] = relationship(back_populates="parts")
