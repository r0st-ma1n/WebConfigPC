// Клиент API бэкенда. Все запросы идут на /api (в разработке Vite проксирует их на :8000)
import type {
  AiStatus, Category, CheckResult, Component, Option, ParseResult,
  RecommendParams, RecommendResult, Recommendation, Resolution,
} from './types'

export class ApiError extends Error {}

async function request<T>(path: string, body?: unknown): Promise<T> {
  let response: Response
  try {
    response = await fetch(`/api${path}`, {
      method: body === undefined ? 'GET' : 'POST',
      headers: body === undefined ? undefined : { 'Content-Type': 'application/json' },
      body: body === undefined ? undefined : JSON.stringify(body),
    })
  } catch {
    throw new ApiError('Сервер не отвечает. Проверьте, что бэкенд запущен.')
  }
  const data = await response.json().catch(() => null)
  if (!response.ok) {
    // FastAPI возвращает текст ошибки в поле detail (строка или список ошибок валидации)
    const detail = data?.detail
    throw new ApiError(typeof detail === 'string' ? detail : 'Проверьте введённые параметры.')
  }
  return data as T
}

/** Событие потока объяснения (формат — в backend/app/ai/service.py, explain_stream) */
export type ExplainEvent =
  | { delta: string }
  | { done: true; source: 'llm' | 'template'; text?: string }

/** Читает NDJSON-поток объяснения и передаёт события в onEvent по мере прихода. */
async function explainStream(
  params: RecommendParams, partIds: number[], tier: string | null,
  onEvent: (e: ExplainEvent) => void, signal: AbortSignal,
): Promise<void> {
  const response = await fetch('/api/ai/explain/stream', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ ...params, part_ids: partIds, tier }),
    signal,
  })
  if (!response.ok || !response.body) throw new ApiError('Не удалось получить объяснение.')

  const reader = response.body.pipeThrough(new TextDecoderStream()).getReader()
  let buffer = ''
  for (;;) {
    const { value, done } = await reader.read()
    if (done) break
    buffer += value
    // Событие может прийти разрезанным на части — обрабатываем только целые строки
    const lines = buffer.split('\n')
    buffer = lines.pop() ?? ''
    for (const line of lines) if (line.trim()) onEvent(JSON.parse(line) as ExplainEvent)
  }
}

export const api = {
  components: (category: Category) => request<Component[]>(`/components?category=${category}`),
  options: (partIds: number[], category: Category) =>
    request<Option[]>('/components/options', { part_ids: partIds, category }),
  check: (partIds: number[], complete: boolean, resolution: Resolution | null) =>
    request<CheckResult>('/compatibility/check', { part_ids: partIds, complete, resolution }),
  recommend: (params: RecommendParams) => request<RecommendResult>('/recommend', params),
  evaluate: (params: RecommendParams, partIds: number[]) =>
    request<Recommendation>('/recommend/evaluate', { ...params, part_ids: partIds }),
  aiStatus: () => request<AiStatus>('/ai/status'),
  parse: (text: string) => request<ParseResult>('/ai/parse', { text }),
  explainStream,
}
