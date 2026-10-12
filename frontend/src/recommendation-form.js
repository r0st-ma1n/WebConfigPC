export const EXAMPLES = [
  'Хочу играть в 1440p до 120 тысяч',
  'Компьютер для монтажа видео за 180к, лучше на Intel',
  'Для учёбы и офиса, бюджет 45 000',
]

export function updateRecommendParams(params, patch) {
  return { ...params, ...patch }
}

export function selectExample(example) {
  return example
}
