# Веб-конфигуратор сборки ПК с рекомендательной системой

Учебный проект: система подбирает сборки ПК под бюджет и сценарий пользователя,
объясняет выбор и предлагает замены.

## Требования

- Python 3.14 и [uv](https://docs.astral.sh/uv/)
- Docker с Docker Compose
- Node.js 20+ (для фронтенда)

## Запуск

```bash
# 1. Настройки окружения
cp .env.example .env

# 2. База данных (PostgreSQL в Docker, порт на хосте 5433)
docker compose up -d

# 3. Зависимости бэкенда
uv sync

# 4. Миграции и тестовые данные (из папки backend)
cd backend
uv run alembic upgrade head
uv run python -m app.seed
```

## Тесты

```bash
uv run pytest
```

## Схема БД

Используется наследование таблиц (joined table inheritance): общие поля всех
комплектующих хранятся в `components`, характеристики категории — в отдельной
таблице, связанной с `components` по `id` (1:1).

| Таблица | Поля |
|---|---|
| `components` | id, category, brand, name, price_rub, perf_score (0–100), power_w, price_updated_at |
| `cpus` | socket, cores, threads, base_ghz, boost_ghz, memory_types[], has_igpu, includes_cooler, multicore_score |
| `gpus` | chip, vram_gb, length_mm, recommended_psu_w |
| `motherboards` | socket, chipset, form_factor, memory_type, memory_slots, max_memory_gb, m2_slots |
| `rams` | memory_type, capacity_gb, modules, speed_mhz |
| `storages` | kind (NVMe / SATA_SSD / HDD), interface (M.2 / SATA), capacity_gb |
| `psus` | wattage, efficiency |
| `cases` | supported_form_factors[], max_gpu_length_mm, max_cooler_height_mm, max_radiator_mm |
| `coolers` | kind (air / aio), height_mm, radiator_mm, sockets[], max_tdp_w |

`perf_score` — оценка производительности внутри категории. У процессоров это
игровая производительность, а многопоточная (рендер, видео) хранится отдельно
в `cpus.multicore_score`. Тестовые данные лежат в `backend/app/seed/components.json`.
Цены примерные и служат только для демонстрации.
