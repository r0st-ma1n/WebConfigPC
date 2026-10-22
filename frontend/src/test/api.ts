// Подмена fetch: тесты отвечают на запросы к /api без запущенного бэкенда
import { vi } from 'vitest'

type Reply = { status?: number; json: unknown }
type Handler = (path: string, body: unknown, method: string) => Reply | undefined

/** Справочники, которые страницы запрашивают при монтировании */
const defaults: Handler = (path) => {
  if (path.startsWith('/api/components')) return { json: [] }
  if (path === '/api/ai/status') return { json: { enabled: false, provider: 'none', model: '' } }
  if (path === '/api/auth/me') return { status: 401, json: { detail: 'Нужно войти в аккаунт.' } }
}

export function mockApi(handler: Handler = () => undefined) {
  return vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
    const path = String(input)
    const body = init?.body ? JSON.parse(String(init.body)) : undefined
    const method = init?.method ?? 'GET'
    const reply = handler(path, body, method) ?? defaults(path, body, method)
    if (!reply) throw new Error(`Неожиданный запрос в тесте: ${method} ${path}`)
    // У ответа 204 не бывает тела
    return new Response(reply.status === 204 ? null : JSON.stringify(reply.json), {
      status: reply.status ?? 200, headers: { 'Content-Type': 'application/json' },
    })
  })
}

/** Тела запросов, отправленных на путь */
export function requestsTo(fetchMock: ReturnType<typeof mockApi>, path: string) {
  return fetchMock.mock.calls
    .filter(([input]) => String(input) === path)
    .map(([, init]) => JSON.parse(String(init?.body)))
}
