"""Каталог комплектующих и ручной режим сборки."""

from fastapi import APIRouter, Depends

from app.compatibility import candidate_errors, check_build
from app.models import Category, Component
from app.repository import build_from_ids, get_parts
from app.schemas import CheckIn, CheckOut, ComponentOut, OptionOut, OptionsIn

router = APIRouter(prefix="/api", tags=["Комплектующие"])


@router.get("/components", response_model=list[ComponentOut])
def list_components(category: Category | None = None, parts: list[Component] = Depends(get_parts)):
    return [ComponentOut.from_model(p) for p in parts if category is None or p.category == category]


@router.post("/components/options", response_model=list[OptionOut])
def component_options(body: OptionsIn, parts: list[Component] = Depends(get_parts)):
    """Варианты для шага ручной сборки: все детали категории с отметкой совместимости.

    Совместимые идут первыми, внутри — по цене. Несовместимые возвращаются с причиной:
    фронтенд по умолчанию их скрывает, но может показать, почему деталь не подходит.
    """
    build = build_from_ids(parts, body.part_ids)
    options = []
    for part in (p for p in parts if p.category == body.category):
        errors = candidate_errors(build, part)
        options.append(
            OptionOut(
                component=ComponentOut.from_model(part),
                compatible=not errors,
                reasons=[e.message for e in errors],
            )
        )
    options.sort(key=lambda o: (not o.compatible, o.component.price_rub))
    return options


@router.post("/compatibility/check", response_model=CheckOut)
def check_compatibility(body: CheckIn, parts: list[Component] = Depends(get_parts)):
    build = build_from_ids(parts, body.part_ids)
    return CheckOut.from_result(check_build(build, complete=body.complete, balance_resolution=body.resolution))
