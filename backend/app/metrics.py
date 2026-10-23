"""Метрики Prometheus: GET /metrics (вне /api, поэтому nginx наружу его не отдаёт).

Бэкенд работает в несколько процессов (воркеры uvicorn), и у каждого свои счётчики.
Если задан PROMETHEUS_MULTIPROC_DIR, процессы пишут значения в файлы этой папки,
а /metrics собирает их вместе — иначе Prometheus видел бы только тот воркер,
которому случайно достался запрос. В Docker папка очищается при каждом старте.
Без переменной (разработка, тесты) метрики хранятся в памяти процесса.
"""

import os
import time

from prometheus_client import (
    CONTENT_TYPE_LATEST,
    REGISTRY,
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)
from prometheus_client.multiprocess import MultiProcessCollector
from starlette.types import ASGIApp, Message, Receive, Scope, Send

# Границы корзин гистограмм: от быстрых ответов каталога до подбора под нагрузкой
_BUCKETS = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30)

HTTP_REQUESTS = Counter("http_requests_total", "HTTP-запросы к API", ["method", "route", "status"])
HTTP_DURATION = Histogram("http_request_duration_seconds", "Время ответа API", ["method", "route"], buckets=_BUCKETS)
# livesum: сумма по живым воркерам (у упавшего воркера значение не застревает)
HTTP_IN_PROGRESS = Gauge(
    "http_requests_in_progress", "Запросы, которые обрабатываются сейчас", multiprocess_mode="livesum"
)

RECOMMEND_CACHE = Counter("recommend_cache_total", "Обращения к кэшу результатов подбора", ["result"])
RECOMMEND_DURATION = Histogram(
    "recommend_compute_seconds", "Время самого подбора (без ответов из кэша)", buckets=_BUCKETS
)
RATE_LIMITED = Counter("rate_limited_total", "Запросы, отклонённые лимитом (429)", ["limiter"])
AI_RESPONSES = Counter(
    "ai_responses_total", "Ответы сценариев с ИИ по источнику: llm, rules, template", ["kind", "source"]
)
REDIS_BREAKER_TRIPS = Counter("redis_breaker_trips_total", "Сколько раз Redis отключался после ошибки")
CATALOG_RELOADS = Counter("catalog_reloads_total", "Загрузки каталога из базы в память процесса")


class Timer:
    """with Timer(histogram): ... — записывает длительность блока."""

    def __init__(self, histogram: Histogram):
        self.histogram = histogram

    def __enter__(self) -> None:
        self.start = time.perf_counter()

    def __exit__(self, *exc: object) -> None:
        self.histogram.observe(time.perf_counter() - self.start)


def render() -> tuple[bytes, str]:
    """Текст для /metrics и его Content-Type."""
    if os.environ.get("PROMETHEUS_MULTIPROC_DIR"):
        registry = CollectorRegistry()
        MultiProcessCollector(registry)
        return generate_latest(registry), CONTENT_TYPE_LATEST
    return generate_latest(REGISTRY), CONTENT_TYPE_LATEST


class MetricsMiddleware:
    """Считает запросы и время ответа по шаблону маршрута.

    Шаблон (/api/builds/{slug}), а не путь (/api/builds/eNJS9Snb): иначе каждая ссылка
    на сборку стала бы отдельным временным рядом, и Prometheus раздулся бы от них.
    Запросы мимо маршрутов (404) попадают в route="unmatched"."""

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["path"] == "/metrics":
            await self.app(scope, receive, send)
            return

        status = 500
        start = time.perf_counter()

        async def send_with_status(message: Message) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
            await send(message)

        HTTP_IN_PROGRESS.inc()
        try:
            await self.app(scope, receive, send_with_status)
        finally:
            HTTP_IN_PROGRESS.dec()
            # Маршрут FastAPI кладёт в scope при сопоставлении — к этому моменту он уже известен
            route = getattr(scope.get("route"), "path", "unmatched")
            HTTP_REQUESTS.labels(scope["method"], route, str(status)).inc()
            HTTP_DURATION.labels(scope["method"], route).observe(time.perf_counter() - start)
