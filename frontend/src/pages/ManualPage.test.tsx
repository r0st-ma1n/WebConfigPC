import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import { mockApi, requestsTo } from '../test/api'
import { cpu, intelCpu, motherboard } from '../test/fixtures'
import type { CheckResult, Option } from '../types'
import { ManualPage } from './ManualPage'

const prices: Record<number, number> = { [cpu.id]: cpu.price_rub, [intelCpu.id]: intelCpu.price_rub, [motherboard.id]: motherboard.price_rub }

/** Бэкенд ручной сборки: Intel несовместим с уже выбранной AM5-платой, проверка суммирует цены */
function mockManualApi(issues: CheckResult['issues'] = []) {
  return mockApi((path, body) => {
    const { part_ids, category } = body as { part_ids: number[]; category?: string }
    if (path === '/api/components/options') {
      const options: Option[] = category === 'cpu'
        ? [
            { component: cpu, compatible: true, reasons: [] },
            { component: intelCpu, compatible: false, reasons: ['Сокет LGA1700 не подходит к плате AM5'] },
          ]
        : category === 'motherboard' ? [{ component: motherboard, compatible: true, reasons: [] }] : []
      return { json: options }
    }
    if (path === '/api/compatibility/check') {
      const total = part_ids.reduce((sum, id) => sum + prices[id], 0)
      return { json: { is_compatible: issues.length === 0, issues, total_price: total, estimated_power_w: 200, recommended_psu_w: 450 } }
    }
  })
}

const steps = () => within(screen.getByRole('navigation', { name: 'Шаги сборки' }))
const currentStep = () => steps().getAllByRole('button').find((b) => b.getAttribute('aria-current') === 'step')

describe('ручная сборка', () => {
  it('показывает только совместимые детали, остальные — по запросу и с причиной', async () => {
    mockManualApi()
    render(<ManualPage />)

    expect(await screen.findByRole('button', { name: /AMD Ryzen 5 7600/ })).toBeEnabled()
    expect(screen.queryByRole('button', { name: /Intel Core i5-14400F/ })).not.toBeInTheDocument()

    await userEvent.click(screen.getByRole('checkbox', { name: /Показать несовместимые \(1\)/ }))

    expect(screen.getByRole('button', { name: /Intel Core i5-14400F/ })).toBeDisabled()
    expect(screen.getByText('Сокет LGA1700 не подходит к плате AM5')).toBeInTheDocument()
  })

  it('после выбора детали переходит к следующему шагу и учитывает её в вариантах и итоге', async () => {
    const fetchMock = mockManualApi()
    render(<ManualPage />)

    await userEvent.click(await screen.findByRole('button', { name: /AMD Ryzen 5 7600/ }))

    expect(currentStep()).toHaveTextContent('Материнская плата')
    expect(steps().getByRole('button', { name: /Процессор/ })).toHaveTextContent('AMD Ryzen 5 7600')
    expect(await screen.findByRole('button', { name: /MSI PRO B650M-A/ })).toBeInTheDocument()
    expect(requestsTo(fetchMock, '/api/components/options')).toContainEqual({ part_ids: [cpu.id], category: 'motherboard' })
    expect(await screen.findByText('18 000 ₽')).toHaveClass('summary-total')
    expect(screen.getByText('1 из 8')).toBeInTheDocument()
  })

  it('подсказывает, что шаг можно пропустить, если кулер идёт с процессором', async () => {
    mockManualApi()
    render(<ManualPage />)
    await userEvent.click(await screen.findByRole('button', { name: /AMD Ryzen 5 7600/ }))
    await userEvent.click(steps().getByRole('button', { name: /Охлаждение/ }))

    expect(screen.getByText(/Кулер идёт в комплекте с процессором/)).toBeInTheDocument()
  })

  it('фильтрует варианты поиском по названию', async () => {
    mockManualApi()
    render(<ManualPage />)
    await userEvent.click(await screen.findByRole('checkbox', { name: /Показать несовместимые/ }))
    await userEvent.type(screen.getByRole('searchbox', { name: 'Поиск по названию' }), 'intel')

    expect(screen.getByRole('button', { name: /Intel Core i5-14400F/ })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /AMD Ryzen 5 7600/ })).not.toBeInTheDocument()
  })

  it('показывает проблемы совместимости из проверки', async () => {
    mockManualApi([{ level: 'warning', code: 'psu', message: 'Блок питания не выбран.', part_ids: [] }])
    render(<ManualPage />)
    await userEvent.click(await screen.findByRole('button', { name: /AMD Ryzen 5 7600/ }))

    expect(await screen.findByText('Блок питания не выбран.')).toBeInTheDocument()
    expect(screen.queryByText('Пока всё совместимо.')).not.toBeInTheDocument()
  })
})
