"""Точка входа FastAPI: uvicorn app.main:app --reload (из папки backend)."""
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import ai, components, recommend
from app.recommender import RecommendError

app = FastAPI(
    title="Конфигуратор ПК",
    description="Подбор сборок ПК под бюджет и сценарий с объяснением выбора",
    version="1.0.0",
)

# Фронтенд в режиме разработки работает на другом порту (Vite, 5173)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(components.router)
app.include_router(recommend.router)
app.include_router(ai.router)


@app.exception_handler(RecommendError)
def recommend_error_handler(_: Request, exc: RecommendError) -> JSONResponse:
    """Понятная ошибка подбора (например, «бюджета не хватает») — код 422 и текст для пользователя."""
    return JSONResponse(status_code=422, content={"detail": str(exc)})


@app.get("/api/health", tags=["Служебное"])
def health():
    return {"status": "ok"}
