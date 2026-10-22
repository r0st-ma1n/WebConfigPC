"""Сохранённые сборки. Тесты работают с настоящим PostgreSQL (фикстура session в conftest.py)."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app import saved_builds
from app.db import get_session
from app.main import app
from app.models import Component, SavedBuild

REQUEST = {"budget": 120_000, "scenario": "gaming", "resolution": "1440p"}


@pytest.fixture
def client(session):
    app.dependency_overrides[get_session] = lambda: session
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def recommended(client) -> dict:
    """Оптимальная сборка из подбора по каталогу в базе."""
    recs = client.post("/api/recommend", json=REQUEST).json()["recommendations"]
    return next(r for r in recs if r["tier"] == "optimal")


def save(client, part_ids: list[int], **extra):
    return client.post("/api/builds", json={**REQUEST, "part_ids": part_ids, **extra})


def ids(rec: dict) -> list[int]:
    return [p["id"] for p in rec["parts"]]


def test_save_and_open_by_link(client, recommended):
    response = save(client, ids(recommended), tier="optimal")
    assert response.status_code == 201
    slug = response.json()["slug"]
    assert len(slug) == 8

    data = client.get(f"/api/builds/{slug}").json()
    assert ids(data["recommendation"]) == ids(recommended)  # порядок деталей сохраняется
    assert data["recommendation"]["tier"] == "optimal"
    assert data["params"]["budget"] == REQUEST["budget"]
    assert data["saved_price"] == recommended["total_price"] == data["recommendation"]["total_price"]


def test_price_change_after_saving_is_visible(client, session, recommended):
    slug = save(client, ids(recommended)).json()["slug"]
    gpu = session.get(Component, next(p["id"] for p in recommended["parts"] if p["category"] == "gpu"))
    gpu.price_rub += 5_000
    session.flush()

    data = client.get(f"/api/builds/{slug}").json()
    assert data["saved_price"] == recommended["total_price"]
    assert data["recommendation"]["total_price"] == recommended["total_price"] + 5_000


def test_same_storage_twice_can_be_saved(client, recommended):
    storage = next(p["id"] for p in recommended["parts"] if p["category"] == "storage")
    slug = save(client, [*ids(recommended), storage]).json()["slug"]
    assert ids(client.get(f"/api/builds/{slug}").json()["recommendation"]).count(storage) == 2


def test_incomplete_build_rejected(client, recommended):
    response = save(client, ids(recommended)[:3])
    assert response.status_code == 422
    assert "неполная" in response.json()["detail"]


def test_unknown_part_rejected(client, recommended):
    assert save(client, [*ids(recommended)[:-1], 999_999]).status_code == 404


def test_unknown_and_malformed_slugs(client):
    assert client.get("/api/builds/nope1234").status_code == 404
    assert client.get("/api/builds/bad%20slug").status_code == 422


def test_slug_collision_is_retried(client, session, recommended, monkeypatch):
    codes = iter(["same-one", "same-one", "other-01"])
    monkeypatch.setattr(saved_builds.secrets, "token_urlsafe", lambda _: next(codes))
    assert save(client, ids(recommended)).json()["slug"] == "same-one"
    # Второй раз первый код занят: база отвергает его, и берётся следующий
    assert save(client, ids(recommended)).json()["slug"] == "other-01"
    assert session.scalar(select(SavedBuild).where(SavedBuild.slug == "other-01")) is not None
