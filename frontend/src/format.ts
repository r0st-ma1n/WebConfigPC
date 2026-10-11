import type { Category, Component, Scenario } from './types'

const rubFormat = new Intl.NumberFormat('ru-RU')

export const rub = (value: number) => `${rubFormat.format(value)} ₽`

/** Цена со знаком: +12 000 ₽ / −4 000 ₽ */
export const rubDelta = (value: number) => `${value > 0 ? '+' : '−'}${rub(Math.abs(value))}`

// Порядок категорий фиксирован: от него зависят цвета на полосе бюджета
export const CATEGORIES: Category[] = ['cpu', 'gpu', 'motherboard', 'ram', 'storage', 'psu', 'case', 'cooler']

export const CATEGORY_TITLES: Record<Category, string> = {
  cpu: 'Процессор',
  gpu: 'Видеокарта',
  motherboard: 'Материнская плата',
  ram: 'Оперативная память',
  storage: 'Накопитель',
  psu: 'Блок питания',
  case: 'Корпус',
  cooler: 'Охлаждение',
}

export const SCENARIO_TITLES: Record<Scenario, string> = {
  gaming: 'Игры',
  workstation: 'Видео и 3D',
  office: 'Офис и учёба',
}

/** Склонение: plural(5, ['ядро', 'ядра', 'ядер']) -> 'ядер' */
export function plural(n: number, forms: [string, string, string]): string {
  const mod10 = n % 10
  const mod100 = n % 100
  if (mod10 === 1 && mod100 !== 11) return forms[0]
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) return forms[1]
  return forms[2]
}

const capacity = (gb: number) => (gb >= 1000 ? `${gb / 1000} ТБ` : `${gb} ГБ`)

/** Короткая строка ключевых характеристик детали для списков */
export function keySpecs(part: Component): string {
  const s = part.specs as Record<string, any>
  switch (part.category) {
    case 'cpu':
      return [
        s.socket,
        `${s.cores} ${plural(s.cores, ['ядро', 'ядра', 'ядер'])} / ${s.threads} ${plural(s.threads, ['поток', 'потока', 'потоков'])}`,
        `до ${s.boost_ghz} ГГц`,
        s.has_igpu ? 'встроенная графика' : null,
        s.includes_cooler ? 'кулер в комплекте' : null,
      ].filter(Boolean).join(', ')
    case 'gpu':
      return `${s.vram_gb} ГБ видеопамяти, длина ${s.length_mm} мм, ${part.power_w} Вт`
    case 'motherboard':
      return `${s.socket}, чипсет ${s.chipset}, ${s.form_factor}, ${s.memory_type}, слотов M.2: ${s.m2_slots}`
    case 'ram':
      return `${s.memory_type}, ${s.capacity_gb} ГБ (${s.modules} × ${s.capacity_gb / s.modules} ГБ), ${s.speed_mhz} МГц`
    case 'storage': {
      const kinds: Record<string, string> = { NVMe: 'NVMe SSD', SATA_SSD: 'SATA SSD', HDD: 'жёсткий диск' }
      return `${kinds[s.kind]}, ${capacity(s.capacity_gb)}`
    }
    case 'psu':
      return `${s.wattage} Вт, ${s.efficiency}`
    case 'case':
      return `${(s.supported_form_factors as string[]).join(', ')}; видеокарта до ${s.max_gpu_length_mm} мм, кулер до ${s.max_cooler_height_mm} мм`
    case 'cooler':
      return s.kind === 'aio'
        ? `жидкостное, радиатор ${s.radiator_mm} мм, до ${s.max_tdp_w} Вт`
        : `воздушное, высота ${s.height_mm} мм, до ${s.max_tdp_w} Вт`
  }
}
