// Подмена fetch: тесты отвечают на запросы к /api без запущенного бэкенда
import { vi } from 'vitest'

type Reply = { status?: number; json: unknown }
type Handler = (path: string, body: unknown) => Reply | undefined

/** Справочники, которые страницы запрашивают при монтировании */
const defaults: Handler = (path) => {
  if (path.startsWith('/api/components')) return { json: [] }
  if (path === '/api/ai/status') return { json: { enabled: false, provider: 'none', model: '' } }
}

export function mockApi(handler: Handler = () => undefined) {
  return vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
    const path = String(input)
    const body = init?.body ? JSON.parse(String(init.body)) : undefined
    const reply = handler(path, body) ?? defaults(path, body)
    if (!reply) throw new Error(`Неожиданный запрос в тесте: ${path}`)
    return new Response(JSON.stringify(reply.json), {
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
