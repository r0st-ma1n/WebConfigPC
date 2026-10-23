"""Точка входа FastAPI: uvicorn app.main:app --reload (из папки backend)."""

import logging

import redis
from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.api import ai, auth, builds, components, recommend
from app.config import settings
from app.db import get_session
from app.metrics import MetricsMiddleware, render
from app.observability import RequestContextMiddleware, setup_logging
from app.recommender import RecommendError
from app.redis_client import breaker as redis_breaker
from app.redis_client import get_redis

setup_logging(settings.log_json, settings.log_level)
log = logging.getLogger(__name__)

app = FastAPI(
    title="Конфигуратор ПК",
    description="Подбор сборок ПК под бюджет и сценарий с объяснением выбора",
    version="1.0.0",
)

# Фронтенд в режиме разработки работает на другом порту (Vite, 5173)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    # Cookie сессии с другого адреса фронтенда (в Docker и с прокси Vite адрес тот же)
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID"],
)
app.add_middleware(MetricsMiddleware)
# Добавлен последним, поэтому выполняется первым и видит все запросы
app.add_middleware(RequestContextMiddleware)

app.include_router(components.router)
app.include_router(recommend.router)
app.include_router(ai.router)
app.include_router(auth.router)
app.include_router(builds.router)


@app.exception_handler(RecommendError)
def recommend_error_handler(_: Request, exc: RecommendError) -> JSONResponse:
    """Понятная ошибка подбора (например, «бюджета не хватает») — код 422 и текст для пользователя."""
    return JSONResponse(status_code=422, content={"detail": str(exc)})


@app.get("/metrics", include_in_schema=False)
def metrics() -> Response:
    """Метрики для Prometheus. Путь вне /api: nginx его наружу не отдаёт."""
    body, content_type = render()
    return Response(body, media_type=content_type)


@app.get("/api/health", tags=["Служебное"])
def health():
    """Процесс жив (liveness): отвечает, даже если база недоступна."""
    return {"status": "ok"}


@app.get("/api/health/ready", tags=["Служебное"])
def ready(session: Session = Depends(get_session)):
    """Готов обслуживать запросы (readiness): база отвечает.

    Состояние Redis только сообщается: без него лимиты и кэш каталога работают
    в памяти процесса, поэтому недоступный Redis не повод снимать экземпляр с балансировки."""
    redis_status = _redis_status()
    try:
        session.execute(text("SELECT 1"))
    except SQLAlchemyError:
        log.exception("База данных недоступна")
        return JSONResponse(
            status_code=503, content={"status": "unavailable", "database": "error", "redis": redis_status}
        )
    return {"status": "ok", "database": "ok", "redis": redis_status}


def _redis_status() -> str:
    client = get_redis()
    if client is None:
        return "disabled"
    if redis_breaker.tripped:  # Redis уже проверяет фоновый поток, ждать таймаута незачем
        return "error"
    try:
        client.ping()
    except redis.RedisError as e:
        redis_breaker.trip(e)
        return "error"
    return "ok"
