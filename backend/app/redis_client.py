"""Подключение к Redis. Redis необязателен: без REDIS_URL приложение работает как раньше.

Через Redis экземпляры бэкенда делят общее состояние: счётчики ограничения запросов
и номер версии каталога (см. rate_limit.py и repository.py).
"""

import logging
import threading
import time
from collections.abc import Callable
from functools import cache

import redis
from redis.backoff import NoBackoff
from redis.retry import Retry

from app.config import settings

log = logging.getLogger(__name__)

# Как часто после ошибки проверять, ожил ли Redis
REDIS_PAUSE_SECONDS = 5.0


@cache
def get_redis() -> redis.Redis | None:
    """Общий клиент (внутри пул соединений, им можно пользоваться из разных потоков)."""
    if not settings.redis_url:
        return None
    # Короткие таймауты и без повторов: если Redis недоступен, запрос не должен ждать,
    # у вызывающего кода всегда есть запасной вариант без Redis
    return redis.Redis.from_url(
        settings.redis_url,
        socket_connect_timeout=0.5,
        socket_timeout=0.5,
        retry=Retry(NoBackoff(), 0),
        decode_responses=True,
    )


class Breaker:
    """Предохранитель: после первой ошибки запросы к Redis не обращаются вовсе.

    Если Redis упал, каждый запрос сначала ждал бы таймаута соединения, а если пропало
    его имя в сети Docker — ещё и ответа DNS (несколько секунд). Поэтому после ошибки
    все пользуются запасными вариантами, а доступность Redis раз в pause секунд проверяет
    фоновый поток. Когда Redis отвечает, предохранитель сам включает его обратно."""

    def __init__(self, probe: Callable[[], object], pause: float = REDIS_PAUSE_SECONDS):
        self.probe = probe
        self.pause = pause
        self._tripped = threading.Event()
        self._lock = threading.Lock()

    @property
    def tripped(self) -> bool:
        return self._tripped.is_set()

    def trip(self, error: Exception) -> None:
        with self._lock:
            if self._tripped.is_set():
                return
            self._tripped.set()
        log.warning("Redis недоступен, лимиты и кэш каталога работают без него: %s", error)
        threading.Thread(target=self._recover, name="redis-recover", daemon=True).start()

    def _recover(self) -> None:
        while self._tripped.is_set():
            time.sleep(self.pause)
            try:
                self.probe()
            except redis.RedisError:
                continue
            log.info("Redis снова доступен")
            self._tripped.clear()

    def reset(self) -> None:
        self._tripped.clear()


def _ping() -> None:
    client = get_redis()
    if client is not None:
        client.ping()


# Один на процесс: если Redis не ответил лимитеру, кэшу каталога тоже не нужно его ждать
breaker = Breaker(_ping)
