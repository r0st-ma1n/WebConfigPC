#!/usr/bin/env bash
# Прогон нагрузочных тестов для таблицы в README: каждый сценарий при разном числе
# воркеров, с кэшем подбора и без. Стек должен быть собран: docker compose up -d --build
#
#   loadtest/bench.sh                 # все замеры (~15 минут)
#   DURATION=20s loadtest/bench.sh    # быстрее, но менее точно
set -euo pipefail
cd "$(dirname "$0")/.."
export MSYS_NO_PATHCONV=1  # Git Bash на Windows не должен переделывать пути внутри контейнера
DURATION=${DURATION:-60s}

restart_backend() {  # $1 — воркеров, $2 — время жизни кэша подбора (0 — без кэша)
  WEB_CONCURRENCY=$1 RECOMMEND_CACHE_SECONDS=$2 docker compose up -d backend >/dev/null 2>&1
  sleep 3
  until [ "$(docker inspect -f '{{.State.Health.Status}}' pcbuilder-backend)" = healthy ]; do sleep 1; done
  docker exec pcbuilder-redis redis-cli --scan --pattern 'cache:recommend:*' | xargs -r docker exec -i pcbuilder-redis redis-cli del >/dev/null
}

k6() {  # $1 — подпись, остальное — переменные для k6.js
  local label=$1; shift
  echo "=== $label"
  # --no-deps: иначе compose пересоздаст бэкенд с настройками по умолчанию
  docker compose --profile loadtest run --rm --no-deps -q k6 run -q -e DURATION="$DURATION" "$@" /scripts/k6.js 2>&1 \
    | grep -E "\{ name:|http_reqs\.|http_req_failed\.|recommend_cache_hits|dropped_iterations" || true
}

for workers in 2 8; do
  restart_backend "$workers" 0
  k6 "лёгкие запросы, $workers воркера, 50 пользователей" -e SCENARIO=catalog -e VUS=50
  k6 "подбор без кэша, $workers воркера, 16 пользователей" -e SCENARIO=recommend -e VUS=16
  for rate in 10 20; do
    k6 "смесь без кэша, $workers воркера, $rate сценариев/с" -e SCENARIO=mixed -e RATE=$rate
  done

  restart_backend "$workers" 3600
  k6 "подбор с кэшем (с пустого), $workers воркера, 16 пользователей" -e SCENARIO=recommend -e VUS=16
  for rate in 10 20 40; do
    k6 "смесь с кэшем, $workers воркера, $rate сценариев/с" -e SCENARIO=mixed -e RATE=$rate
  done
done
