"""ИИ: статус, разбор свободного запроса, объяснение сборки."""
from fastapi import APIRouter, Depends

from app.ai import service
from app.ai.factory import get_provider
from app.models import Component
from app.recommender import Tier, evaluate_build
from app.repository import build_from_ids, get_parts
from app.schemas import AiStatusOut, ExplainIn, ExplainOut, ParseIn, ParseOut

router = APIRouter(prefix="/api/ai", tags=["ИИ"])


@router.get("/status", response_model=AiStatusOut)
def ai_status():
    """Подключена ли LLM. Фронтенд по этому флагу решает, что показывать."""
    provider = get_provider()
    if provider is None:
        return AiStatusOut(enabled=False, provider="none", model="")
    return AiStatusOut(enabled=True, provider=provider.name, model=provider.model)


@router.post("/parse", response_model=ParseOut)
def parse(body: ParseIn, parts: list[Component] = Depends(get_parts)):
    params, source, notes = service.parse_request(body.text, parts)
    return ParseOut(params=params, source=source, notes=notes)


@router.post("/explain", response_model=ExplainOut)
def explain(body: ExplainIn, parts: list[Component] = Depends(get_parts)):
    build = build_from_ids(parts, body.part_ids)
    tier = Tier(body.tier) if body.tier else None
    rec = evaluate_build(parts, body.to_request(), build, tier)
    text, source = service.explain(rec.facts)
    return ExplainOut(text=text, source=source)
