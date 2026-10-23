"""Загрузка комплектующих из базы данных и кэш каталога."""

import logging
import threading
import time
from collections.abc import Callable

import redis
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.db import SessionLocal
from app.domain import Build
from app.metrics import CATALOG_RELOADS
from app.models import Component
from app.redis_client import breaker, get_redis

log = logging.getLogger(__name__)

# Номер версии каталога в Redis. Его увеличивает каждый, кто меняет детали или цены
CATALOG_VERSION_KEY = "catalog:version"


def load_parts(session: Session) -> list[Component]:
    """Весь каталог одним запросом (JOIN со всеми таблицами характеристик).
    Каталог небольшой, поэтому подбор работает с ним целиком в памяти."""
    return list(session.scalars(select(Component).order_by(Component.category, Component.price_rub)))


def catalog_version() -> str | None:
    """Текущая версия каталога из Redis. None — Redis не настроен или недоступен."""
    client = get_redis()
    if client is None or breaker.tripped:
        return None
    try:
        value = client.get(CATALOG_VERSION_KEY)
    except redis.RedisError as e:
        breaker.trip(e)  # пока Redis недоступен, каталог перечитывается по TTL
        return None
    return None if value is None else str(value)


def bump_catalog_version() -> None:
    """Сообщает всем экземплярам бэкенда, что каталог изменился. Вызывается после commit."""
    client = get_redis()
    if client is None:
        return
    try:
        client.incr(CATALOG_VERSION_KEY)
    except redis.RedisError as e:
        # Не страшно: кэш всё равно устареет через CATALOG_CACHE_SECONDS
        log.warning("Не удалось обновить версию каталога в Redis: %s", e)


def _load_from_db() -> list[Component]:
    # Своя сессия, а не сессия запроса: откат в обработчике запроса сбросил бы
    # загруженные атрибуты объектов, которые потом читают другие запросы
    with SessionLocal() as session:
        return load_parts(session)


class CatalogCache:
    """Каталог в памяти процесса, готовыми объектами: подбору не нужно ни запроса к базе,
    ни разбора JSON. Каталог перечитывается, когда в Redis поменялась версия
    (после импорта цен или сида) или прошло ttl секунд.

    Объекты используются только для чтения, поэтому их можно отдавать разным потокам."""

    def __init__(
        self,
        ttl: float,
        loader: Callable[[], list[Component]] = _load_from_db,
        version: Callable[[], str | None] = catalog_version,
        clock: Callable[[], float] = time.monotonic,
    ):
        self.ttl = ttl
        self.loader = loader
        self.version = version
        self.clock = clock
        self._parts: list[Component] | None = None
        self._version: str | None = None
        self._loaded_at = 0.0
        self._lock = threading.Lock()

    def _fresh(self, version: str | None) -> bool:
        return version == self._version and self.clock() - self._loaded_at < self.ttl

    def get(self) -> list[Component]:
        # Версия читается до загрузки: если импорт закоммитят во время загрузки, версия
        # в Redis уже будет другой, и следующий запрос перечитает каталог ещё раз
        version = self.version()
        parts = self._parts
        if parts is not None and self._fresh(version):
            return parts
        with self._lock:
            # Пока ждали блокировку, каталог мог перечитать другой поток
            parts = self._parts
            if parts is None or not self._fresh(version):
                parts = self.loader()
                CATALOG_RELOADS.inc()
                self._parts, self._version, self._loaded_at = parts, version, self.clock()
            return parts

    def clear(self) -> None:
        with self._lock:
            self._parts = None


catalog_cache = CatalogCache(settings.catalog_cache_seconds)


def get_parts() -> list[Component]:
    """Зависимость FastAPI. В тестах подменяется каталогом из JSON."""
    return catalog_cache.get()


def build_from_ids(parts: list[Component], part_ids: list[int]) -> Build:
    by_id = {p.id: p for p in parts}
    unknown = [i for i in part_ids if i not in by_id]
    if unknown:
        raise HTTPException(404, f"Комплектующие не найдены: {unknown}")
    return Build.from_parts([by_id[i] for i in part_ids])
