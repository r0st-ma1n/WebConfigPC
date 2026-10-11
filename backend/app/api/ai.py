"""ИИ: статус, разбор свободного запроса, объяснение сборки."""
import asyncio
import json
import logging
import threading
from collections.abc import AsyncIterator, Generator

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from app.ai import service
from app.ai.factory import get_provider
from app.models import Component
from app.recommender import Tier, evaluate_build
from app.repository import build_from_ids, get_parts
from app.schemas import AiStatusOut, ExplainIn, ExplainOut, ParseIn, ParseOut

log = logging.getLogger(__name__)

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
    return StreamingResponse(_ndjson(events), media_type="application/x-ndjson")


async def _ndjson(events: Generator[dict]) -> AsyncIterator[str]:
    """События -> строки NDJSON.

    Генератор событий синхронный, поэтому читается в отдельном потоке. Когда клиент уходит
    (выбрал другую сборку, закрыл страницу), этот поток сам закрывает генератор, а с ним
    закрывается и соединение с LLM. Иначе модель дописывала бы брошенный ответ, занимая
    видеокарту, и следующее объяснение ждало бы её."""
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue[dict | None] = asyncio.Queue()
    stop = threading.Event()

    def put(item: dict | None) -> None:
        try:
            loop.call_soon_threadsafe(queue.put_nowait, item)
        except RuntimeError:  # цикл событий уже закрыт — сервер останавливается
            pass

    def pump() -> None:
        try:
            for event in events:
                if stop.is_set():
                    break
                put(event)
        except Exception:
            log.exception("Сбой при потоковой выдаче объяснения")
        finally:
            events.close()  # закрываем в этом же потоке, где генератор работал
            put(None)

    threading.Thread(target=pump, daemon=True).start()
    try:
        while (event := await queue.get()) is not None:
            yield json.dumps(event, ensure_ascii=False) + "\n"
    finally:
        stop.set()
