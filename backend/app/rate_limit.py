"""Ограничение частоты запросов.

- К LLM: каждый запрос к модели стоит денег (облачный API) или занимает видеокарту
  (локальная модель), поэтому один клиент не должен отправлять их без ограничений.
- Ко входу и регистрации: защита от перебора паролей.

С REDIS_URL счётчики общие для всех экземпляров бэкенда (и всех воркеров uvicorn).
Без Redis они в памяти процесса: каждый воркер считает сам, и лимит фактически
умножается на число воркеров.
"""

import logging
import math
import threading
import time
import uuid
from collections import deque
from collections.abc import Callable
from typing import Protocol

import redis
from fastapi import HTTPException, Request

from app.config import settings
from app.redis_client import Breaker, get_redis
from app.redis_client import breaker as redis_breaker

log = logging.getLogger(__name__)


class Limiter(Protocol):
    limit: int

    def hit(self, key: str) -> float | None: ...


class RateLimiter:
    """Скользящее окно: не больше limit запросов за последние window секунд с одного адреса."""

    def __init__(self, limit: int, window: float = 60.0, clock: Callable[[], float] = time.monotonic):
        self.limit = limit
        self.window = window
        self.clock = clock
        self._hits: dict[str, deque[float]] = {}
        # Синхронные эндпоинты FastAPI выполняются в пуле потоков
        self._lock = threading.Lock()

    def hit(self, key: str) -> float | None:
        """Учитывает запрос. None — можно; иначе через сколько секунд освободится место."""
        now = self.clock()
        with self._lock:
            hits = self._hits.setdefault(key, deque())
            while hits and hits[0] <= now - self.window:
                hits.popleft()
            if len(hits) >= self.limit:
                return hits[0] + self.window - now
            hits.append(now)
            if len(self._hits) > 10_000:  # не копим адреса, которые давно не приходили
                self._hits = {k: v for k, v in self._hits.items() if v[-1] > now - self.window}
            return None


# То же скользящее окно в отсортированном множестве Redis: элемент — запрос, score — его время.
# Скрипт выполняется атомарно, поэтому два воркера не могут одновременно занять последнее место.
# Время берётся у Redis, а не у воркеров: часы разных машин могут расходиться.
_SLIDING_WINDOW = """
local now_parts = redis.call('TIME')
local now = now_parts[1] * 1000 + math.floor(now_parts[2] / 1000)
local limit = tonumber(ARGV[1])
local window = tonumber(ARGV[2])
redis.call('ZREMRANGEBYSCORE', KEYS[1], '-inf', now - window)
if redis.call('ZCARD', KEYS[1]) >= limit then
    local oldest = redis.call('ZRANGE', KEYS[1], 0, 0, 'WITHSCORES')
    return tonumber(oldest[2]) + window - now
end
redis.call('ZADD', KEYS[1], now, ARGV[3])
redis.call('PEXPIRE', KEYS[1], window)
return -1
"""


class RedisRateLimiter:
    """Скользящее окно в Redis, общее для всех экземпляров бэкенда.

    Если Redis недоступен, запросы считает локальный RateLimiter: защита слабее
    (у каждого воркера свой счётчик), но API продолжает работать."""

    def __init__(
        self, client: redis.Redis, name: str, limit: int, window: float = 60.0, breaker: Breaker = redis_breaker
    ):
        self.limit = limit
        self.window = window
        self._prefix = f"ratelimit:{name}:"
        self._script = client.register_script(_SLIDING_WINDOW)
        self._fallback = RateLimiter(limit, window)
        self._breaker = breaker

    def hit(self, key: str) -> float | None:
        if self._breaker.tripped:
            return self._fallback.hit(key)
        try:
            # uuid — уникальный элемент множества: два запроса в одну миллисекунду не сливаются в один
            args: list[int | str] = [self.limit, int(self.window * 1000), uuid.uuid4().hex]
            wait_ms = int(self._script(keys=[self._prefix + key], args=args))
        except redis.RedisError as e:
            self._breaker.trip(e)
            return self._fallback.hit(key)
        return None if wait_ms < 0 else wait_ms / 1000


def make_limiter(name: str, limit: int) -> Limiter:
    client = get_redis()
    return RedisRateLimiter(client, name, limit) if client else RateLimiter(limit)


ai_limiter = make_limiter("ai", settings.ai_rate_limit_per_minute)
auth_limiter = make_limiter("auth", settings.auth_rate_limit_per_minute)


def _enforce(limiter: Limiter, request: Request, message: str) -> None:
    if limiter.limit <= 0:  # 0 — ограничение выключено
        return
    client = request.client.host if request.client else "unknown"
    retry_after = limiter.hit(client)
    if retry_after is not None:
        raise HTTPException(429, message, headers={"Retry-After": str(math.ceil(retry_after))})


def limit_ai(request: Request) -> None:
    """Зависимость FastAPI для эндпоинтов, которые обращаются к LLM."""
    _enforce(ai_limiter, request, "Слишком много запросов к ИИ. Попробуйте через минуту.")


def limit_auth(request: Request) -> None:
    """Зависимость FastAPI для входа и регистрации."""
    _enforce(auth_limiter, request, "Слишком много попыток входа. Попробуйте через минуту.")
