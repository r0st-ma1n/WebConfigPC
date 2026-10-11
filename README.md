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

## Модуль совместимости

`backend/app/compatibility/`. Сборка (`app/domain.py`, класс `Build`) проверяется
набором независимых правил. Каждое правило — функция `(сборка) -> список нарушений`.
Нарушение содержит уровень (`error` — собрать нельзя, `warning` — можно, но есть риск),
машинный код, понятный текст и id затронутых деталей.

| Правило | Уровень | Что проверяет |
|---|---|---|
| `cpu_motherboard_socket` | error | сокет процессора и платы |
| `cooler_socket` | error | кулер поддерживает сокет |
| `cooler_tdp` | warning | кулер справляется с тепловыделением CPU |
| `ram_type` | error | тип памяти: RAM ↔ плата ↔ процессор |
| `ram_slots_and_capacity` | error | число модулей ≤ слотов, объём ≤ максимума платы |
| `m2_slots` | error | хватает слотов M.2 |
| `board_form_factor` | error | форм-фактор платы поддерживается корпусом |
| `gpu_length` | error | видеокарта помещается в корпус |
| `cooler_fits_case` | error | высота кулера / размер радиатора СЖО |
| `psu_power` | error / warning | мощность БП ≥ потребления; запас ≥ 30% и не ниже рекомендации производителя GPU |
| `cpu_gpu_balance` | warning | процессор не ограничивает видеокарту и не избыточен для неё |

Для законченной сборки (`complete=True`) дополнительно проверяется, что выбраны
все обязательные детали, есть вывод изображения (видеокарта или встроенная графика)
и охлаждение (отдельный кулер или боксовый).

**Потребление сборки** — сумма `power_w` всех деталей. **Рекомендуемый БП** —
потребление × 1,3, округлённое вверх до 50 Вт, но не ниже рекомендации производителя видеокарты.

**Баланс CPU/GPU** (`app/balance.py`). Шкалы оценок CPU и GPU разные, поэтому
процессор считается достаточным, если `cpu_score ≥ gpu_score × K`. Здесь K зависит от
разрешения: 0,9 для 1080p, 0,75 для 1440p, 0,55 для 4K. Чем выше разрешение,
тем больше нагрузка на видеокарту. Процессор избыточен, если `cpu_score > gpu_score × 2,7`.

**Ручной режим** использует `filter_compatible(сборка, кандидаты)`: деталь
показывается, если её установка не порождает ошибок, в которых участвует она сама.
