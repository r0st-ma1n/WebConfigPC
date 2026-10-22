"""Пользователи, сессии и «Мои сборки». Тесты работают с настоящим PostgreSQL (фикстура session в conftest.py)."""

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, update

from app import rate_limit
from app.auth import COOKIE_NAME
from app.db import get_session
from app.main import app
from app.models import User, UserSession
from app.rate_limit import RateLimiter

PASSWORD = "correct horse battery"
REQUEST = {"budget": 120_000, "scenario": "gaming", "resolution": "1440p"}


@pytest.fixture
def make_client(session, monkeypatch):
    """Несколько клиентов — как несколько браузеров: у каждого свои cookie."""
    monkeypatch.setattr(rate_limit, "auth_limiter", RateLimiter(0))
    app.dependency_overrides[get_session] = lambda: session
    clients: list[TestClient] = []

    def make() -> TestClient:
        client = TestClient(app)
        clients.append(client)
        return client

    yield make
    for c in clients:
        c.close()
    app.dependency_overrides.clear()


@pytest.fixture
def client(make_client):
    return make_client()


def register(client, email="ivan@example.com", password=PASSWORD):
    return client.post("/api/auth/register", json={"email": email, "password": password})


def login(client, email="ivan@example.com", password=PASSWORD):
    return client.post("/api/auth/login", json={"email": email, "password": password})


def save_build(client) -> str:
    rec = next(
        r for r in client.post("/api/recommend", json=REQUEST).json()["recommendations"] if r["tier"] == "optimal"
    )
    body = {**REQUEST, "part_ids": [p["id"] for p in rec["parts"]], "tier": "optimal"}
    return client.post("/api/builds", json=body).json()["slug"]


# ---------- Регистрация и вход ----------


def test_register_logs_in_and_stores_only_hashes(client, session):
    response = register(client, email="Ivan@Example.com")

    assert response.status_code == 201
    assert response.json()["email"] == "ivan@example.com"
    assert client.get("/api/auth/me").json()["email"] == "ivan@example.com"

    user = session.scalar(select(User).where(User.email == "ivan@example.com"))
    assert user.password_hash.startswith("$argon2id$")
    stored = session.scalar(select(UserSession.token_hash).where(UserSession.user_id == user.id))
    assert stored != client.cookies[COOKIE_NAME]


def test_session_cookie_is_http_only_and_scoped_to_api(client):
    cookie = register(client).headers["set-cookie"].lower()
    assert "httponly" in cookie
    assert "samesite=lax" in cookie
    assert "path=/api" in cookie


def test_email_is_unique_case_insensitive(client):
    register(client)
    response = register(client, email="IVAN@example.com")
    assert response.status_code == 409


@pytest.mark.parametrize(
    "body",
    [
        {"email": "not-an-email", "password": PASSWORD},
        {"email": "ivan@example.com", "password": "short"},
        {"email": "ivan@example.com", "password": "x" * 129},
    ],
)
def test_invalid_credentials_rejected(client, body):
    assert client.post("/api/auth/register", json=body).status_code == 422


def test_login_with_wrong_password_or_unknown_email_gives_same_error(make_client):
    register(make_client())
    wrong_password = login(make_client(), password="wrong password")
    unknown_email = login(make_client(), email="nobody@example.com")

    assert wrong_password.status_code == unknown_email.status_code == 401
    assert wrong_password.json() == unknown_email.json()


def test_login_works_from_another_device(make_client):
    register(make_client())
    other = make_client()

    assert login(other, email="IVAN@example.com").status_code == 200
    assert other.get("/api/auth/me").status_code == 200


def test_login_is_rate_limited(client, monkeypatch):
    monkeypatch.setattr(rate_limit, "auth_limiter", RateLimiter(2))
    statuses = [login(client).status_code for _ in range(3)]
    assert statuses == [401, 401, 429]


# ---------- Сессии ----------


def test_anonymous_user_is_not_logged_in(client):
    assert client.get("/api/auth/me").status_code == 401


def test_logout_ends_session(client, session):
    register(client)
    assert client.post("/api/auth/logout").status_code == 204

    assert client.get("/api/auth/me").status_code == 401
    assert session.scalar(select(UserSession)) is None


def test_stolen_cookie_is_useless_after_logout(client, make_client):
    register(client)
    attacker = make_client()
    attacker.cookies.set(COOKIE_NAME, client.cookies[COOKIE_NAME], path="/api")
    assert attacker.get("/api/auth/me").status_code == 200

    client.post("/api/auth/logout")
    assert attacker.get("/api/auth/me").status_code == 401


def test_logout_everywhere_ends_all_sessions(make_client):
    laptop, phone = make_client(), make_client()
    register(laptop)
    login(phone)

    assert phone.post("/api/auth/logout-all").status_code == 204

    assert laptop.get("/api/auth/me").status_code == 401
    assert phone.get("/api/auth/me").status_code == 401


def test_expired_session_is_rejected(client, session):
    register(client)
    session.execute(update(UserSession).values(expires_at=datetime.now(UTC) - timedelta(seconds=1)))

    assert client.get("/api/auth/me").status_code == 401


# ---------- Мои сборки ----------


def test_my_builds_require_login(client):
    assert client.get("/api/builds").status_code == 401


def test_saved_build_appears_in_my_builds(client):
    register(client)
    slug = save_build(client)

    builds = client.get("/api/builds").json()
    assert [(b["slug"], b["title"]) for b in builds] == [(slug, "Оптимальная")]
    assert builds[0]["saved_price"] > 0
    assert client.get(f"/api/builds/{slug}").json()["owned"] is True


def test_guest_build_belongs_to_nobody(make_client):
    guest, ivan = make_client(), make_client()
    slug = save_build(guest)
    register(ivan)

    assert ivan.get("/api/builds").json() == []
    assert ivan.get(f"/api/builds/{slug}").json()["owned"] is False
    assert ivan.delete(f"/api/builds/{slug}").status_code == 403


def test_only_owner_can_delete_build(make_client):
    owner, stranger = make_client(), make_client()
    register(owner)
    register(stranger, email="petr@example.com")
    slug = save_build(owner)

    assert stranger.delete(f"/api/builds/{slug}").status_code == 403
    assert owner.delete(f"/api/builds/{slug}").status_code == 204
    assert owner.get(f"/api/builds/{slug}").status_code == 404
    assert owner.get("/api/builds").json() == []
