"""Redis: общий лимит запросов для нескольких воркеров, кэш каталога и результатов подбора.

Тесты с Redis идут на отдельной базе (TEST_REDIS_URL, по умолчанию база 15 Redis из
docker-compose) и пропускаются, если Redis не запущен. Само приложение в тестах работает
без Redis, поэтому остальные тесты от него не зависят.
"""

import os
import threading
import time
import uuid

import pytest
import redis
from fastapi.testclient import TestClient
from redis.backoff import NoBackoff
from redis.retry import Retry

from app import main, redis_client, repository, response_cache
from app.rate_limit import RedisRateLimiter
from app.redis_client import Breaker
from app.repository import CatalogCache, bump_catalog_version, catalog_version, get_parts
from app.seed import load_catalog

TEST_REDIS_URL = os.environ.get("TEST_REDIS_URL", "redis://localhost:6380/15")
CATALOG = load_catalog(with_ids=True)


@pytest.fixture
def client_redis():
    client = redis.Redis.from_url(TEST_REDIS_URL, socket_connect_timeout=0.5, decode_responses=True)
    try:
        client.ping()
    except redis.RedisError:  # без Docker на Windows бывает не отказ, а таймаут
        pytest.skip("Redis не запущен")
    yield client
    client.flushdb()
    client.close()


def dead_redis() -> redis.Redis:
    """Клиент, который получает ошибку соединения: на этом порту никто не слушает."""
    return redis.Redis(port=1, socket_connect_timeout=0.2, retry=Retry(NoBackoff(), 0), decode_responses=True)


@pytest.fixture(autouse=True)
def reset_breaker():
    """Предохранитель общий для процесса: ошибка Redis в одном тесте не должна влиять на другие."""
    redis_client.breaker.reset()
    yield
    redis_client.breaker.reset()


class FakeProbe:
    """Проверка доступности Redis для предохранителя: падает, пока alive=False."""

    def __init__(self):
        self.alive = False

    def __call__(self):
        if not self.alive:
            raise redis.ConnectionError("Redis всё ещё недоступен")


def wait_until(condition, timeout=2.0):
    deadline = time.monotonic() + timeout
    while not condition():
        assert time.monotonic() < deadline, "условие не выполнилось"
        time.sleep(0.01)


# ---------- Лимит запросов ----------


def test_redis_limiter_allows_up_to_limit_then_blocks(client_redis):
    limiter = RedisRateLimiter(client_redis, f"t-{uuid.uuid4().hex}", limit=3, window=60)
    assert [limiter.hit("a") for _ in range(3)] == [None, None, None]
    assert limiter.hit("a") == pytest.approx(60, abs=1)
    assert limiter.hit("b") is None  # у другого клиента свой счётчик


def test_redis_limiter_is_shared_between_workers(client_redis):
    """Два экземпляра лимитера — как два воркера uvicorn: лимит у них один на двоих."""
    name = f"t-{uuid.uuid4().hex}"
    worker1 = RedisRateLimiter(client_redis, name, limit=4, window=60)
    worker2 = RedisRateLimiter(client_redis, name, limit=4, window=60)
    assert [worker1.hit("a"), worker2.hit("a"), worker1.hit("a"), worker2.hit("a")] == [None] * 4
    assert worker1.hit("a") is not None
    assert worker2.hit("a") is not None


def test_redis_limiter_window_slides(client_redis):
    limiter = RedisRateLimiter(client_redis, f"t-{uuid.uuid4().hex}", limit=2, window=0.3)
    assert limiter.hit("a") is None
    assert limiter.hit("a") is None
    assert limiter.hit("a") is not None
    time.sleep(0.35)
    assert limiter.hit("a") is None


def test_redis_limiter_concurrent_requests_do_not_exceed_limit(client_redis):
    """Скрипт атомарный: из 50 одновременных запросов проходят ровно limit."""
    limiter = RedisRateLimiter(client_redis, f"t-{uuid.uuid4().hex}", limit=10, window=60)
    results: list[float | None] = []
    lock = threading.Lock()

    def hit():
        r = limiter.hit("a")
        with lock:
            results.append(r)

    threads = [threading.Thread(target=hit) for _ in range(50)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert results.count(None) == 10


def test_redis_limiter_falls_back_to_memory_when_redis_is_down():
    limiter = RedisRateLimiter(dead_redis(), "t", limit=2, window=60, breaker=Breaker(FakeProbe()))
    assert limiter.hit("a") is None
    assert limiter.hit("a") is None
    assert limiter.hit("a") is not None  # лимит работает, хоть и в памяти процесса


def test_breaker_skips_redis_until_background_probe_succeeds():
    """После ошибки запросы не ждут Redis, а сразу идут в запасной счётчик.
    Когда Redis оживает, фоновая проверка включает его обратно."""
    calls = 0
    client = dead_redis()
    original = client.execute_command

    def counting(*args, **kwargs):
        nonlocal calls
        calls += 1
        return original(*args, **kwargs)

    client.execute_command = counting  # type: ignore[method-assign]
    probe = FakeProbe()
    breaker = Breaker(probe, pause=0.02)
    limiter = RedisRateLimiter(client, "t", limit=100, window=60, breaker=breaker)
    for _ in range(5):
        limiter.hit("a")
    assert calls == 1
    assert breaker.tripped
    time.sleep(0.1)  # несколько неудачных фоновых проверок
    assert breaker.tripped
    probe.alive = True
    wait_until(lambda: not breaker.tripped)
    limiter.hit("a")
    assert calls == 2


# ---------- Кэш каталога ----------


class FakeClock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


class CountingLoader:
    def __init__(self, delay: float = 0):
        self.calls = 0
        self.delay = delay

    def __call__(self):
        time.sleep(self.delay)
        self.calls += 1
        return list(CATALOG)


def test_catalog_cache_reuses_parts_until_ttl():
    clock, loader = FakeClock(), CountingLoader()
    cache = CatalogCache(ttl=60, loader=loader, version=lambda: None, clock=clock)
    first = cache.get()
    clock.now += 59
    assert cache.get() is first
    assert loader.calls == 1
    clock.now += 2
    assert cache.get() is not first
    assert loader.calls == 2


def test_catalog_cache_reloads_when_version_changes():
    version = "1"
    loader = CountingLoader()
    cache = CatalogCache(ttl=3600, loader=loader, version=lambda: version, clock=FakeClock())
    cache.get()
    cache.get()
    version = "2"  # импорт цен в другом процессе
    cache.get()
    assert loader.calls == 2


def test_catalog_cache_loads_once_for_concurrent_requests():
    loader = CountingLoader(delay=0.05)
    cache = CatalogCache(ttl=60, loader=loader, version=lambda: None)
    threads = [threading.Thread(target=cache.get) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert loader.calls == 1


def test_bump_catalog_version_invalidates_cache(client_redis, monkeypatch):
    monkeypatch.setattr(repository, "get_redis", lambda: client_redis)
    loader = CountingLoader()
    cache = CatalogCache(ttl=3600, loader=loader)  # версия читается из Redis
    cache.get()
    cache.get()
    bump_catalog_version()
    cache.get()
    assert loader.calls == 2
    assert catalog_version() == "1"


def test_catalog_works_when_redis_is_down(monkeypatch):
    monkeypatch.setattr(repository, "get_redis", dead_redis)
    bump_catalog_version()  # ошибка только в логе
    assert catalog_version() is None
    loader = CountingLoader()
    cache = CatalogCache(ttl=60, loader=loader)
    cache.get()
    cache.get()
    assert loader.calls == 1  # без версии кэш живёт по TTL


# ---------- Кэш результатов подбора ----------

REQUEST = {"budget": 120_000, "scenario": "gaming", "resolution": "1440p"}


@pytest.fixture
def api(client_redis, monkeypatch):
    monkeypatch.setattr(response_cache, "get_redis", lambda: client_redis)
    main.app.dependency_overrides[get_parts] = lambda: CATALOG
    with TestClient(main.app) as c:
        yield c
    main.app.dependency_overrides.clear()


def test_recommend_second_identical_request_comes_from_cache(api):
    first = api.post("/api/recommend", json=REQUEST)
    second = api.post("/api/recommend", json=REQUEST)
    assert first.headers["X-Cache"] == "MISS"
    assert second.headers["X-Cache"] == "HIT"
    assert second.json() == first.json()


def test_recommend_cache_depends_on_params(api):
    api.post("/api/recommend", json=REQUEST)
    other = api.post("/api/recommend", json={**REQUEST, "budget": 125_000})
    assert other.headers["X-Cache"] == "MISS"


def test_recommend_cache_misses_after_price_change(api):
    """Ключ включает цены каталога: после импорта цен старый результат не вернётся."""
    api.post("/api/recommend", json=REQUEST)
    gpu = next(p for p in CATALOG if p.category == "gpu")
    old_price = gpu.price_rub
    gpu.price_rub += 1_000
    try:
        response = api.post("/api/recommend", json=REQUEST)
    finally:
        gpu.price_rub = old_price
    assert response.headers["X-Cache"] == "MISS"
    assert api.post("/api/recommend", json=REQUEST).headers["X-Cache"] == "HIT"  # старая цена — старый ключ


def test_recommend_works_without_redis_cache(monkeypatch):
    monkeypatch.setattr(response_cache, "get_redis", dead_redis)
    main.app.dependency_overrides[get_parts] = lambda: CATALOG
    try:
        with TestClient(main.app) as c:
            response = c.post("/api/recommend", json=REQUEST)
    finally:
        main.app.dependency_overrides.clear()
    assert response.status_code == 200
    assert response.headers["X-Cache"] == "MISS"
    assert len(response.json()["recommendations"]) == 3


# ---------- Готовность ----------


@pytest.mark.parametrize(
    ("get_redis", "status"),
    [(lambda: None, "disabled"), (dead_redis, "error")],
)
def test_ready_reports_redis_but_does_not_fail(monkeypatch, get_redis, status):
    """Без Redis приложение работает, поэтому он не влияет на код ответа readiness."""
    monkeypatch.setattr(main, "get_redis", get_redis)
    with TestClient(main.app) as c:
        response = c.get("/api/health/ready")
    if response.json()["database"] == "error":
        pytest.skip("PostgreSQL не запущен")
    assert response.status_code == 200
    assert response.json()["redis"] == status


def test_ready_does_not_wait_for_redis_when_breaker_is_tripped(monkeypatch):
    def must_not_connect():
        raise AssertionError("readiness не должен обращаться к Redis, пока он отключён")

    client = dead_redis()
    client.ping = must_not_connect  # type: ignore[method-assign]
    monkeypatch.setattr(main, "get_redis", lambda: client)
    redis_client.breaker.trip(redis.ConnectionError("тест"))
    with TestClient(main.app) as c:
        response = c.get("/api/health/ready")
    assert response.json()["redis"] == "error"


def test_ready_reports_redis_ok(client_redis, monkeypatch):
    monkeypatch.setattr(main, "get_redis", lambda: client_redis)
    with TestClient(main.app) as c:
        response = c.get("/api/health/ready")
    assert response.json()["redis"] == "ok"
