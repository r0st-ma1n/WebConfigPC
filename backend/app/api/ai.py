"""ИИ: статус, разбор свободного запроса, объяснение сборки."""
import json

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

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


def _facts(body: ExplainIn, parts: list[Component]) -> dict:
    """Факты о сборке, по которым модель пишет объяснение."""
    build = build_from_ids(parts, body.part_ids)
    tier = Tier(body.tier) if body.tier else None
    return evaluate_build(parts, body.to_request(), build, tier).facts


@router.post("/explain", response_model=ExplainOut)
def explain(body: ExplainIn, parts: list[Component] = Depends(get_parts)):
    text, source = service.explain(_facts(body, parts))
    return ExplainOut(text=text, source=source)


@router.post("/explain/stream")
def explain_stream(body: ExplainIn, parts: list[Component] = Depends(get_parts)):
    """То же объяснение, но текст приходит по мере генерации: NDJSON, одно событие
    на строку (формат событий — в service.explain_stream)."""
    # Факты считаются до ответа: ошибки подбора вернутся обычным кодом 422, а не посреди потока
    events = service.explain_stream(_facts(body, parts))
    return StreamingResponse(
        (json.dumps(e, ensure_ascii=False) + "\n" for e in events),
        media_type="application/x-ndjson",
    )
