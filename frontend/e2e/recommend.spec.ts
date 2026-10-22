import { expect, test } from '@playwright/test'
import { recommendResult } from '../src/test/fixtures.ts'

test.beforeEach(async ({ page }) => {
  await page.route('**/api/**', (route) => {
    const path = new URL(route.request().url()).pathname
    if (path === '/api/ai/status') return route.fulfill({ json: { enabled: false, provider: 'none', model: '' } })
    if (path === '/api/components') return route.fulfill({ json: [] })
    if (path === '/api/recommend') return route.fulfill({ json: recommendResult })
    return route.fulfill({ status: 404, json: { detail: `Нет заглушки для ${path}` } })
  })
})

test('с главной страницы можно перейти к подбору и получить сборки', async ({ page }) => {
  await page.goto('/')
  await page.getByRole('link', { name: 'Подобрать компьютер' }).click()

  await expect(page).toHaveURL('/recommend')
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('Подберём компьютер под ваши задачи')

  await page.getByRole('button', { name: 'Подобрать сборки' }).click()

  const tiers = page.getByRole('group', { name: 'Варианты сборки' })
  await expect(tiers.getByRole('button', { name: /Оптимальная/ })).toHaveAttribute('aria-pressed', 'true')
  await expect(page.getByText('NVIDIA GeForce RTX 4060 Ti')).toBeVisible()
})
