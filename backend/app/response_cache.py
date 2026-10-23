"""Кэш результатов подбора в Redis.

Подбор — самый тяжёлый запрос: около 0,5 с CPU, и пока он считается, воркер почти
не отвечает на остальные запросы (GIL). Результат зависит только от параметров запроса
и каталога, а параметры у людей повторяются: бюджет выбирается ползунком с шагом 5000 ₽.

В ключ входит отпечаток каталога — id и цены всех деталей. После импорта цен ключи
меняются сами, поэтому устаревший результат вернуть нельзя и сбрасывать кэш не нужно:
старые записи просто истекают, а при нехватке памяти Redis вытесняет давно не нужные
(volatile-lru в docker-compose.yml).
"""

import hashlib

import redis
from pydantic import BaseModel

from app.config import settings
from app.models import Component
from app.redis_client import breaker, get_redis

PREFIX = "cache:recommend:"


def catalog_fingerprint(parts: list[Component]) -> str:
    """Меняется при любом изменении состава каталога или цены. Для 138 деталей — доли миллисекунды."""
    h = hashlib.blake2b(digest_size=16)
    for p in parts:
        h.update(f"{p.id}:{p.price_rub};".encode())
    return h.hexdigest()


def cache_key(body: BaseModel, parts: list[Component]) -> str:
    raw = body.model_dump_json() + catalog_fingerprint(parts)
    return PREFIX + hashlib.blake2b(raw.encode(), digest_size=16).hexdigest()


def get(key: str) -> str | None:
    """Готовый JSON ответа или None. Ошибка Redis — промах, запрос просто посчитается."""
    client = get_redis()
    if client is None or settings.recommend_cache_seconds <= 0 or breaker.tripped:
        return None
    try:
        value = client.get(key)
    except redis.RedisError as e:
        breaker.trip(e)
        return None
    return None if value is None else str(value)


def put(key: str, value: str) -> None:
    client = get_redis()
    if client is None or settings.recommend_cache_seconds <= 0 or breaker.tripped:
        return
    try:
        client.set(key, value, ex=settings.recommend_cache_seconds)
    except redis.RedisError as e:
        breaker.trip(e)
