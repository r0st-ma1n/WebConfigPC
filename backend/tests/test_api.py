"""Smoke-тесты API. Каталог берётся из JSON вместо базы (подмена зависимости get_parts)."""
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.repository import get_parts
from app.seed import load_catalog

CATALOG = load_catalog(with_ids=True)
BY_NAME = {p.name: p for p in CATALOG}


@pytest.fixture(scope="module")
def client():
    app.dependency_overrides[get_parts] = lambda: CATALOG
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def test_components_by_category(client):
    data = client.get("/api/components", params={"category": "cpu"}).json()
    assert len(data) == 23
    assert {"socket", "cores", "memory_types"} <= set(data[0]["specs"])


def test_options_show_only_compatible_first(client):
    cpu = BY_NAME["Ryzen 5 7600"]
    data = client.post("/api/components/options", json={"part_ids": [cpu.id], "category": "motherboard"}).json()
    compatible = [o for o in data if o["compatible"]]
    assert compatible and all(o["component"]["specs"]["socket"] == "AM5" for o in compatible)
    # Несовместимые идут после совместимых и содержат причину
    first_bad = next(i for i, o in enumerate(data) if not o["compatible"])
    assert all(not o["compatible"] for o in data[first_bad:])
    assert "сокет" in data[first_bad]["reasons"][0]


def test_compatibility_check(client):
    ids = [BY_NAME["Ryzen 5 5600"].id, BY_NAME["B650M GAMING X AX"].id]
    data = client.post("/api/compatibility/check", json={"part_ids": ids}).json()
    assert not data["is_compatible"]
    assert any(i["code"] == "socket_mismatch" for i in data["issues"])


def test_unknown_part_id(client):
    assert client.post("/api/compatibility/check", json={"part_ids": [999_999]}).status_code == 404


def test_recommend(client):
    data = client.post("/api/recommend", json={"budget": 120_000, "scenario": "gaming", "resolution": "1440p"}).json()
    assert sum(data["allocation"].values()) == pytest.approx(120_000, abs=10)
    recs = data["recommendations"]
    assert [r["tier"] for r in recs] == ["cheaper", "optimal", "headroom"]
    for r in recs:
        assert r["check"]["is_compatible"]
        assert r["explanation"] and r["explanation_source"] == "template"
        assert len(r["parts"]) >= 7


def test_recommend_validation(client):
    assert client.post("/api/recommend", json={"budget": -5, "scenario": "gaming"}).status_code == 422
    assert client.post("/api/recommend", json={"budget": 100_000, "scenario": "mining"}).status_code == 422


def test_recommend_too_small_budget_message(client):
    response = client.post("/api/recommend", json={"budget": 15_000, "scenario": "gaming"})
    assert response.status_code == 422
    assert "Бюджета не хватает" in response.json()["detail"]


def test_apply_alternative_via_evaluate(client):
    """Применение замены: сборка из part_ids замены оценивается заново."""
    request = {"budget": 120_000, "scenario": "gaming", "resolution": "1440p"}
    rec = client.post("/api/recommend", json=request).json()["recommendations"][0]
    alt = rec["upgrades"][0]
    data = client.post("/api/recommend/evaluate", json={**request, "part_ids": alt["part_ids"]}).json()
    assert data["total_price"] == rec["total_price"] + alt["price_delta"]
    assert data["title"] == "Ваша сборка"


def test_evaluate_incomplete_build(client):
    body = {"budget": 100_000, "scenario": "gaming", "part_ids": [BY_NAME["Ryzen 5 7600"].id]}
    response = client.post("/api/recommend/evaluate", json=body)
    assert response.status_code == 422
    assert "неполная" in response.json()["detail"]


def test_ai_endpoints_without_key(client, monkeypatch):
    # Тест не должен зависеть от того, прописан ли ключ в .env
    import app.ai.service
    import app.api.ai
    monkeypatch.setattr(app.api.ai, "get_provider", lambda: None)
    monkeypatch.setattr(app.ai.service, "get_provider", lambda: None)

    assert client.get("/api/ai/status").json()["enabled"] is False
    parsed = client.post("/api/ai/parse", json={"text": "игровой ПК до 100 тысяч"}).json()
    assert parsed["source"] == "rules"
    assert parsed["params"]["budget"] == 100_000

    rec = client.post("/api/recommend", json={"budget": 100_000, "scenario": "gaming"}).json()["recommendations"][0]
    body = {"budget": 100_000, "scenario": "gaming", "part_ids": [p["id"] for p in rec["parts"]], "tier": rec["tier"]}
    explained = client.post("/api/ai/explain", json=body).json()
    assert explained["source"] == "template"
    assert explained["text"] == rec["explanation"]
