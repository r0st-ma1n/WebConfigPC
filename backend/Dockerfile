# Сборка из корня проекта: docker build -f backend/Dockerfile .
# (зависимости описаны в корневых pyproject.toml и uv.lock)
FROM python:3.14-slim

COPY --from=ghcr.io/astral-sh/uv:0.11.11 /uv /usr/local/bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Сначала только зависимости: этот слой пересобирается, лишь когда меняется uv.lock
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY backend/ ./backend/

RUN useradd --create-home --uid 1000 app
USER app

WORKDIR /app/backend
EXPOSE 8000

# Миграции и начальные данные при каждом старте: оба шага идемпотентны.
# Бэкенд доступен только из сети Compose, поэтому IP клиента из X-Forwarded-For (от nginx)
# можно принимать от любого адреса. Журнал запросов пишет само приложение (с request-id).
# Папка метрик воркеров (PROMETHEUS_MULTIPROC_DIR, см. app/metrics.py) очищается при старте:
# файлы прошлого запуска исказили бы счётчики
CMD ["sh", "-c", "if [ -n \"$PROMETHEUS_MULTIPROC_DIR\" ]; then rm -rf \"$PROMETHEUS_MULTIPROC_DIR\" && mkdir -p \"$PROMETHEUS_MULTIPROC_DIR\"; fi && alembic upgrade head && python -m app.seed --if-empty && exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips=* --no-access-log"]
