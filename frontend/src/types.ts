// Типы данных API генерируются из OpenAPI-схемы бэкенда: src/api-schema.ts (npm run gen:api).
// Здесь — короткие имена для них и типы, которые есть только во фронтенде.
import type { components } from './api-schema.ts'

export type Schemas = components['schemas']

export type Category = Schemas['Category']
export type Scenario = Schemas['Scenario']
export type Resolution = Schemas['Resolution']
export type Platform = Schemas['Platform']
export type Tier = Schemas['Tier']

export type Component = Schemas['ComponentOut']
export type Issue = Schemas['IssueOut']
export type CheckResult = Schemas['CheckOut']
export type Option = Schemas['OptionOut']
export type RecommendParams = Schemas['RecommendIn']
export type Alternative = Schemas['AlternativeOut']
export type Recommendation = Schemas['RecommendationOut']
export type AiStatus = Schemas['AiStatusOut']
export type ParseResult = Schemas['ParseOut']
export type User = Schemas['UserOut']
/** Сохранённая сборка: saved_price — цена на момент сохранения, recommendation.total_price — по текущим ценам */
export type SavedBuild = Schemas['SavedBuildOut']
/** Строка списка «Мои сборки» */
export type SavedBuildSummary = Schemas['SavedBuildSummaryOut']

/** В JSON Schema ключи словаря — просто строки, поэтому здесь они уточнены до категорий */
export type RecommendResult = Omit<Schemas['RecommendOut'], 'allocation'> & {
  allocation: Record<Category, number>
}

export type AppRoute = '/' | '/recommend' | '/manual' | '/info'
export interface NavigationItem { path: AppRoute; label: string }
export interface PresetBuild { name: string; audience: string; startingPrice: number; route: AppRoute }
export interface KnowledgeArticle { id: string; category: string; title: string; summary: string; body: string; readingMinutes: number }
export interface RecommendationFormState { text: string; params: RecommendParams }
