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
  explain: (params: RecommendParams, partIds: number[], tier: string | null) =>
    request<{ text: string; source: 'llm' | 'template' }>('/ai/explain', { ...params, part_ids: partIds, tier }),
}
