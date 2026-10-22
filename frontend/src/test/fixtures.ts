// Ответы API для тестов: компонентных (vitest) и e2e (Playwright)
import type { Component, Recommendation, RecommendResult } from '../types.ts'

export const cpu: Component = {
  id: 1, category: 'cpu', brand: 'AMD', name: 'Ryzen 5 7600', title: 'AMD Ryzen 5 7600',
  price_rub: 18_000, perf_score: 70, power_w: 65,
  specs: { socket: 'AM5', cores: 6, threads: 12, boost_ghz: 5.1, has_igpu: true, includes_cooler: true },
}
export const gpu: Component = {
  id: 2, category: 'gpu', brand: 'NVIDIA', name: 'RTX 4060', title: 'NVIDIA GeForce RTX 4060',
  price_rub: 32_000, perf_score: 60, power_w: 115,
  specs: { vram_gb: 8, length_mm: 240 },
}
const gpuTi: Component = {
  ...gpu, id: 3, name: 'RTX 4060 Ti', title: 'NVIDIA GeForce RTX 4060 Ti', price_rub: 42_000, perf_score: 72,
}
export const intelCpu: Component = {
  id: 4, category: 'cpu', brand: 'Intel', name: 'Core i5-14400F', title: 'Intel Core i5-14400F',
  price_rub: 17_000, perf_score: 68, power_w: 65,
  specs: { socket: 'LGA1700', cores: 10, threads: 16, boost_ghz: 4.7, has_igpu: false, includes_cooler: false },
}
export const motherboard: Component = {
  id: 5, category: 'motherboard', brand: 'MSI', name: 'B650M', title: 'MSI PRO B650M-A',
  price_rub: 14_000, perf_score: 0, power_w: 10,
  specs: { socket: 'AM5', chipset: 'B650', form_factor: 'mATX', memory_type: 'DDR5', m2_slots: 2 },
}

export function recommendation(tier: Recommendation['tier'], title: string, parts: Component[], score: number): Recommendation {
  return {
    tier, title, parts, score,
    total_price: parts.reduce((sum, p) => sum + p.price_rub, 0),
    score_breakdown: {},
    check: { is_compatible: true, issues: [], total_price: 0, estimated_power_w: 250, recommended_psu_w: 450 },
    upgrades: [], savings: [],
    explanation: `Объяснение сборки «${title}».`,
    explanation_source: 'template',
    facts: {},
  }
}

export const recommendResult: RecommendResult = {
  allocation: { cpu: 20_000, gpu: 40_000, motherboard: 12_000, ram: 8_000, storage: 7_000, psu: 6_000, case: 5_000, cooler: 2_000 },
  recommendations: [
    recommendation('cheaper', 'Дешевле', [cpu, gpu], 64),
    recommendation('optimal', 'Оптимальная', [cpu, gpuTi], 75),
  ],
}
