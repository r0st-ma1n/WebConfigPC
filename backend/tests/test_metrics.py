"""Метрики Prometheus: /metrics, метки маршрутов, счётчики кэша подбора и лимитов."""

import pytest
from fastapi.testclient import TestClient
from prometheus_client import REGISTRY

from app import rate_limit
from app.ai import service
from app.main import app
from app.rate_limit import RateLimiter
from app.repository import get_parts
from app.seed import load_catalog

CATALOG = load_catalog(with_ids=True)


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(service, "get_provider", lambda: None)
    app.dependency_overrides[get_parts] = lambda: CATALOG
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def value(name: str, **labels: str) -> float:
    """Текущее значение метрики (0, если таких меток ещё не было)."""
    return REGISTRY.get_sample_value(name, labels) or 0.0


def test_metrics_endpoint_exposes_prometheus_text(client):
    client.get("/api/health")
    response = client.get("/metrics")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    assert "http_requests_total" in response.text
    assert "http_request_duration_seconds_bucket" in response.text


def test_metrics_endpoint_is_not_in_api_docs(client):
    assert "/metrics" not in client.get("/openapi.json").json()["paths"]


def test_requests_are_labelled_by_route_template_not_path(client):
    """Каждая ссылка на сборку не должна становиться отдельным временным рядом."""
    labels = {"method": "DELETE", "route": "/api/builds/{slug}", "status": "401"}
    before = value("http_requests_total", **labels)
    client.delete("/api/builds/abc123")
    client.delete("/api/builds/xyz789")
    assert value("http_requests_total", **labels) == before + 2
    assert value("http_requests_total", method="DELETE", route="/api/builds/abc123", status="401") == 0


def test_unknown_paths_share_one_label(client):
    before = value("http_requests_total", method="GET", route="unmatched", status="404")
    client.get("/api/no-such-endpoint")
    client.get("/wp-login.php")
    assert value("http_requests_total", method="GET", route="unmatched", status="404") == before + 2


def test_request_duration_is_observed(client):
    labels = {"method": "GET", "route": "/api/components"}
    before = value("http_request_duration_seconds_count", **labels)
    client.get("/api/components")
    assert value("http_request_duration_seconds_count", **labels) == before + 1
    assert value("http_requests_in_progress") == 0


def test_recommend_counts_cache_misses_and_compute_time(client):
    misses = value("recommend_cache_total", result="miss")
    computed = value("recommend_compute_seconds_count")
    client.post("/api/recommend", json={"budget": 120_000, "scenario": "gaming", "resolution": "1440p"})
    assert value("recommend_cache_total", result="miss") == misses + 1  # без Redis — всегда промах
    assert value("recommend_compute_seconds_count") == computed + 1


def test_rate_limited_requests_are_counted(client, monkeypatch):
    monkeypatch.setattr(rate_limit, "ai_limiter", RateLimiter(limit=1))
    before = value("rate_limited_total", limiter="ai")
    client.post("/api/ai/parse", json={"text": "игровой ПК за 100 тысяч"})
    assert client.post("/api/ai/parse", json={"text": "игровой ПК за 100 тысяч"}).status_code == 429
    assert value("rate_limited_total", limiter="ai") == before + 1


def test_ai_responses_are_counted_by_source(client):
    before = value("ai_responses_total", kind="parse", source="rules")
    client.post("/api/ai/parse", json={"text": "игровой ПК за 100 тысяч"})
    assert value("ai_responses_total", kind="parse", source="rules") == before + 1
