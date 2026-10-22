// Типы данных API (повторяют Pydantic-схемы бэкенда из backend/app/schemas.py)

export type Category = 'cpu' | 'gpu' | 'motherboard' | 'ram' | 'storage' | 'psu' | 'case' | 'cooler'
export type Scenario = 'gaming' | 'workstation' | 'office'
export type Resolution = '1080p' | '1440p' | '4k'
export type Platform = 'amd' | 'intel'

export interface Component {
  id: number
  category: Category
  brand: string
  name: string
  title: string
  price_rub: number
  perf_score: number
  power_w: number
  specs: Record<string, unknown>
}

export interface Issue {
  level: 'error' | 'warning'
  code: string
  message: string
  part_ids: number[]
}

export interface CheckResult {
  is_compatible: boolean
  issues: Issue[]
  total_price: number
  estimated_power_w: number
  recommended_psu_w: number
}

export interface Option {
  component: Component
  compatible: boolean
  reasons: string[]
}

export interface RecommendParams {
  budget: number
  scenario: Scenario
  resolution: Resolution
  platform: Platform | null
  cpu_id: number | null
  gpu_id: number | null
}

export interface Alternative {
  kind: 'upgrade' | 'saving'
  category: Category
  text: string
  price_delta: number
  score_delta_pct: number
  worth_it: boolean
  new_part: Component
  also_changed: Component[]
  part_ids: number[]
}

export interface Recommendation {
  tier: 'cheaper' | 'optimal' | 'headroom' | null
  title: string
  parts: Component[]
  total_price: number
  score: number
  score_breakdown: Record<string, number>
  check: CheckResult
  upgrades: Alternative[]
  savings: Alternative[]
  explanation: string
  explanation_source: 'template' | 'llm'
  facts: Record<string, unknown>
}

export interface SavedBuild {
  slug: string
  created_at: string
  params: RecommendParams
  /** Цена на момент сохранения; recommendation.total_price — по текущим ценам */
  saved_price: number
  recommendation: Recommendation
  /** Сборку сохранил текущий пользователь */
  owned: boolean
}

/** Строка списка «Мои сборки» */
export interface SavedBuildSummary {
  slug: string
  created_at: string
  title: string
  params: RecommendParams
  saved_price: number
}

export interface User {
  id: number
  email: string
}

export interface RecommendResult {
  allocation: Record<Category, number>
  recommendations: Recommendation[]
}

export interface AiStatus {
  enabled: boolean
  provider: string
  model: string
}

export interface ParseResult {
  params: RecommendParams | null
  source: 'llm' | 'rules'
  notes: string
}

export type AppRoute = '/' | '/recommend' | '/manual' | '/info'
export interface NavigationItem { path: AppRoute; label: string }
export interface PresetBuild { name: string; audience: string; startingPrice: number; route: AppRoute }
export interface KnowledgeArticle { id: string; category: string; title: string; summary: string; body: string; readingMinutes: number }
export interface RecommendationFormState { text: string; params: RecommendParams }
