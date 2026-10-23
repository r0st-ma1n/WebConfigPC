// Нагрузочный тест API через nginx, как ходит браузер.
//
//   docker compose up -d --build
//   docker compose --profile loadtest run --rm k6 run -e SCENARIO=catalog /scripts/k6.js
//
// Сценарии (SCENARIO):
//   catalog   — лёгкие запросы ручной сборки: каталог, варианты деталей, проверка совместимости
//   recommend — подбор сборок (тяжёлый запрос, весь каталог перебирается на CPU)
//   saved     — открытие сохранённой сборки по ссылке (оценка заново по текущим ценам)
//   mixed     — смесь, похожая на живых пользователей, с постоянной частотой запросов (RATE в секунду)
//
// Число виртуальных пользователей — VUS, длительность — DURATION.
// Входа и запросов к ИИ здесь нет: у них свои лимиты (429), их проверяют тесты.

import http from 'k6/http'
import { check } from 'k6'
import { Rate } from 'k6/metrics'

const BASE = __ENV.BASE_URL || 'http://frontend'
const SCENARIO = __ENV.SCENARIO || 'mixed'
const VUS = Number(__ENV.VUS || 20)
const DURATION = __ENV.DURATION || '30s'
const RATE = Number(__ENV.RATE || 20)

const JSON_HEADERS = { headers: { 'Content-Type': 'application/json' } }
const CATEGORIES = ['cpu', 'gpu', 'motherboard', 'ram', 'storage', 'psu', 'case', 'cooler']
const SCENARIO_NAMES = ['gaming', 'workstation', 'office']
const RESOLUTIONS = ['1080p', '1440p', '4k']
// Бюджет — как с ползунка в интерфейсе: от 40 до 300 тыс. с шагом 5000 ₽.
// Вместе со сценарием и разрешением это 477 разных запросов
const BUDGETS = Array.from({ length: 53 }, (_, i) => 40000 + i * 5000)

// Доля ответов подбора из кэша (заголовок X-Cache)
const cacheHits = new Rate('recommend_cache_hits')

const closed = { executor: 'constant-vus', vus: VUS, duration: DURATION }
const SCENARIOS = {
  catalog: { ...closed, exec: 'catalog' },
  recommend: { ...closed, exec: 'recommend' },
  saved: { ...closed, exec: 'saved' },
  mixed: {
    executor: 'constant-arrival-rate',
    exec: 'mixed',
    rate: RATE,
    timeUnit: '1s',
    duration: DURATION,
    preAllocatedVUs: 50,
    maxVUs: 500,
  },
}

export const options = {
  scenarios: { [SCENARIO]: SCENARIOS[SCENARIO] },
  summaryTrendStats: ['med', 'p(95)', 'p(99)', 'max'],
  // Цели по времени ответа (p95). Заодно k6 выводит время по каждому эндпоинту отдельно
  thresholds: {
    http_req_failed: ['rate<0.01'],
    'http_req_duration{name:components}': ['p(95)<300'],
    'http_req_duration{name:options}': ['p(95)<300'],
    'http_req_duration{name:check}': ['p(95)<300'],
    'http_req_duration{name:saved}': ['p(95)<500'],
    'http_req_duration{name:recommend}': ['p(95)<2000'],
  },
}

const pick = (items) => items[Math.floor(Math.random() * items.length)]
const randomRequest = () => ({ budget: pick(BUDGETS), scenario: pick(SCENARIO_NAMES), resolution: pick(RESOLUTIONS) })
const post = (path, body, name, extra = {}) =>
  http.post(`${BASE}${path}`, JSON.stringify(body), { ...JSON_HEADERS, tags: { name }, ...extra })
// 422 у подбора — штатный ответ «бюджета не хватает на этот сценарий», а не сбой
const RECOMMEND_OK = { responseCallback: http.expectedStatuses(200, 422) }

// Один раз до теста: готовая сборка (для проверки совместимости) и ссылка на сохранённую сборку
export function setup() {
  const request = { budget: 120000, scenario: 'gaming', resolution: '1440p' }
  const rec = post('/api/recommend', request, 'setup').json('recommendations.1')
  const partIds = rec.parts.map((p) => p.id)
  const saved = post('/api/builds', { ...request, part_ids: partIds, tier: rec.tier }, 'setup')
  return { partIds, slug: saved.json('slug') }
}

export function catalog(data) {
  const r1 = http.get(`${BASE}/api/components?category=${pick(CATEGORIES)}`, { tags: { name: 'components' } })
  // Шаг ручной сборки: уже выбраны процессор и плата, выбирается память
  const r2 = post('/api/components/options', { part_ids: data.partIds.slice(0, 2), category: 'ram' }, 'options')
  const r3 = post('/api/compatibility/check', { part_ids: data.partIds, complete: true }, 'check')
  check(r1, { 'components 200': (r) => r.status === 200 })
  check(r2, { 'options 200': (r) => r.status === 200 })
  check(r3, { 'check 200': (r) => r.status === 200 })
}

export function recommend() {
  const r = post('/api/recommend', randomRequest(), 'recommend', RECOMMEND_OK)
  check(r, { 'recommend 200 или 422': (res) => res.status === 200 || res.status === 422 })
  if (r.status === 200) cacheHits.add(r.headers['X-Cache'] === 'HIT')
}

export function saved(data) {
  const r = http.get(`${BASE}/api/builds/${data.slug}`, { tags: { name: 'saved' } })
  check(r, { 'saved 200': (res) => res.status === 200 })
}

// Из 10 действий: 6 — ручная сборка, 2 — открыть сохранённую сборку, 2 — подбор
export function mixed(data) {
  const roll = Math.random()
  if (roll < 0.6) catalog(data)
  else if (roll < 0.8) saved(data)
  else recommend()
}
