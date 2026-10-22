"""Служебное: ограничение запросов к ИИ, request-id и логи, проверка готовности, настройки."""

import json
import logging

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from app import rate_limit
from app.ai import service
from app.config import Settings
from app.db import get_session
from app.main import app
from app.observability import JsonFormatter, RequestIdFilter, request_id
from app.rate_limit import RateLimiter
from app.repository import get_parts
from app.seed import load_catalog

CATALOG = load_catalog(with_ids=True)


@pytest.fixture
def client(monkeypatch):
    # Без LLM: тесты не должны зависеть от .env и ждать настоящую модель
    monkeypatch.setattr(service, "get_provider", lambda: None)
    app.dependency_overrides[get_parts] = lambda: CATALOG
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


# ---------- Ограничение запросов ----------


class FakeClock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def test_limiter_allows_up_to_limit_then_blocks():
    clock = FakeClock()
    limiter = RateLimiter(limit=3, window=60, clock=clock)
    assert [limiter.hit("a") for _ in range(3)] == [None, None, None]
    assert limiter.hit("a") == pytest.approx(60)
    assert limiter.hit("b") is None  # у другого клиента свой счётчик


def test_limiter_window_slides():
    clock = FakeClock()
    limiter = RateLimiter(limit=2, window=60, clock=clock)
    limiter.hit("a")
    clock.now += 30
    limiter.hit("a")
    clock.now += 31  # первый запрос вышел из окна, второй ещё нет
    assert limiter.hit("a") is None
    assert limiter.hit("a") == pytest.approx(29)


def test_ai_endpoint_returns_429_with_retry_after(client, monkeypatch):
    monkeypatch.setattr(rate_limit, "ai_limiter", RateLimiter(limit=2))
    for _ in range(2):
        assert client.post("/api/ai/parse", json={"text": "игры за 100к"}).status_code == 200
    response = client.post("/api/ai/parse", json={"text": "игры за 100к"})
    assert response.status_code == 429
    assert int(response.headers["Retry-After"]) > 0
    # Остальной API ограничение не затрагивает
    assert client.get("/api/ai/status").status_code == 200


def test_zero_limit_disables_limiting(client, monkeypatch):
    monkeypatch.setattr(rate_limit, "ai_limiter", RateLimiter(limit=0))
    for _ in range(3):
        assert client.post("/api/ai/parse", json={"text": "офис"}).status_code == 200


# ---------- Request-id и логи ----------


def test_request_id_generated_and_returned(client):
    first = client.get("/api/health").headers["X-Request-ID"]
    second = client.get("/api/health").headers["X-Request-ID"]
    assert first and second and first != second


def test_request_id_taken_from_header(client):
    response = client.get("/api/health", headers={"X-Request-ID": "abc-123"})
    assert response.headers["X-Request-ID"] == "abc-123"


def test_request_is_logged_with_its_id(client, caplog):
    caplog.handler.addFilter(RequestIdFilter())
    with caplog.at_level(logging.INFO, logger="app.request"):
        client.get("/api/health", headers={"X-Request-ID": "trace-me"})
    record = next(r for r in caplog.records if r.name == "app.request")
    assert record.request_id == "trace-me"
    assert (record.method, record.path, record.status) == ("GET", "/api/health", 200)
    assert record.duration_ms >= 0


def test_json_formatter_includes_request_id_and_extra_fields():
    record = logging.LogRecord("app.test", logging.INFO, __file__, 1, "готово %s", ("ok",), None)
    record.duration_ms = 12.5
    token = request_id.set("rid-1")
    try:
        RequestIdFilter().filter(record)
    finally:
        request_id.reset(token)
    data = json.loads(JsonFormatter().format(record))
    assert data["message"] == "готово ok"
    assert data["request_id"] == "rid-1"
    assert data["duration_ms"] == 12.5
    assert data["level"] == "INFO"


# ---------- Проверка готовности ----------


class FakeSession:
    def __init__(self, error: Exception | None = None):
        self.error = error

    def execute(self, _statement):
        if self.error:
            raise self.error


def test_ready_when_database_answers(client):
    app.dependency_overrides[get_session] = lambda: FakeSession()
    response = client.get("/api/health/ready")
    assert response.status_code == 200
    assert response.json()["database"] == "ok"


def test_not_ready_when_database_fails(client):
    error = OperationalError("SELECT 1", {}, Exception("connection refused"))
    app.dependency_overrides[get_session] = lambda: FakeSession(error)
    response = client.get("/api/health/ready")
    assert response.status_code == 503
    assert response.json()["database"] == "error"


# ---------- Настройки ----------


def test_cors_origins_parsed_from_comma_separated_string():
    s = Settings(cors_origins=" https://a.example , https://b.example,", _env_file=None)
    assert s.cors_origin_list == ["https://a.example", "https://b.example"]
