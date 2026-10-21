"""Точка входа FastAPI: uvicorn app.main:app --reload (из папки backend)."""
import logging

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.api import ai, components, recommend
from app.config import settings
from app.db import get_session
from app.observability import RequestContextMiddleware, setup_logging
from app.recommender import RecommendError

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
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID"],
)
# Добавлен последним, поэтому выполняется первым и видит все запросы
app.add_middleware(RequestContextMiddleware)

app.include_router(components.router)
app.include_router(recommend.router)
app.include_router(ai.router)


@app.exception_handler(RecommendError)
def recommend_error_handler(_: Request, exc: RecommendError) -> JSONResponse:
    """Понятная ошибка подбора (например, «бюджета не хватает») — код 422 и текст для пользователя."""
    return JSONResponse(status_code=422, content={"detail": str(exc)})


@app.get("/api/health", tags=["Служебное"])
def health():
    """Процесс жив (liveness): отвечает, даже если база недоступна."""
    return {"status": "ok"}


@app.get("/api/health/ready", tags=["Служебное"])
def ready(session: Session = Depends(get_session)):
    """Готов обслуживать запросы (readiness): база отвечает."""
    try:
        session.execute(text("SELECT 1"))
    except SQLAlchemyError:
        log.exception("База данных недоступна")
        return JSONResponse(status_code=503, content={"status": "unavailable", "database": "error"})
    return {"status": "ok", "database": "ok"}
