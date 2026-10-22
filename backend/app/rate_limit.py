"""Ограничение частоты запросов.

- К LLM: каждый запрос к модели стоит денег (облачный API) или занимает видеокарту
  (локальная модель), поэтому один клиент не должен отправлять их без ограничений.
- Ко входу и регистрации: защита от перебора паролей.

Счётчики хранятся в памяти процесса: для одного экземпляра бэкенда этого достаточно.
При нескольких экземплярах счётчики нужно перенести в общее хранилище (например, Redis).
"""

import math
import threading
import time
from collections import deque
from collections.abc import Callable

from fastapi import HTTPException, Request

from app.config import settings


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


ai_limiter = RateLimiter(settings.ai_rate_limit_per_minute)
auth_limiter = RateLimiter(settings.auth_rate_limit_per_minute)


def _enforce(limiter: RateLimiter, request: Request, message: str) -> None:
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
