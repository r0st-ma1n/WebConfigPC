import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import { mockApi, requestsTo } from '../test/api'
import { recommendResult } from '../test/fixtures'
import type { RecommendParams } from '../types'
import { RecommendPage } from './RecommendPage'

const submitParams = () => userEvent.click(screen.getByRole('button', { name: 'Подобрать сборки' }))
const tiers = () => within(screen.getByRole('group', { name: 'Варианты сборки' }))

describe('подбор по параметрам', () => {
  it('отправляет изменённые параметры, не теряя остальные', async () => {
    const fetchMock = mockApi((path) => path === '/api/recommend' ? { json: recommendResult } : undefined)
    render(<RecommendPage ai={null} />)

    const budget = screen.getByLabelText('Бюджет в рублях')
    await userEvent.clear(budget)
    await userEvent.type(budget, '150000')
    await userEvent.click(screen.getByRole('radio', { name: '4K' }))
    await submitParams()

    expect(requestsTo(fetchMock, '/api/recommend')).toEqual([{
      budget: 150_000, scenario: 'gaming', resolution: '4k', platform: null, cpu_id: null, gpu_id: null,
    }])
  })

  it('прячет выбор разрешения для неигровых сценариев', async () => {
    mockApi()
    render(<RecommendPage ai={null} />)
    expect(screen.getByRole('radiogroup', { name: 'Разрешение' })).toBeInTheDocument()

    await userEvent.click(screen.getByRole('radio', { name: 'Офис и учёба' }))

    expect(screen.getByRole('radio', { name: 'Офис и учёба' })).toHaveAttribute('aria-checked', 'true')
    expect(screen.queryByRole('radiogroup', { name: 'Разрешение' })).not.toBeInTheDocument()
  })

  it('показывает варианты сборки и по умолчанию открывает оптимальную', async () => {
    mockApi((path) => path === '/api/recommend' ? { json: recommendResult } : undefined)
    render(<RecommendPage ai={null} />)
    await submitParams()

    expect(tiers().getByRole('button', { name: /Оптимальная/ })).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByRole('heading', { level: 2, name: 'Оптимальная' })).toBeInTheDocument()

    await userEvent.click(tiers().getByRole('button', { name: /Дешевле/ }))
    expect(screen.getByRole('heading', { level: 2, name: 'Дешевле' })).toBeInTheDocument()
  })

  it('показывает текст ошибки от сервера', async () => {
    mockApi((path) => path === '/api/recommend' ? { status: 422, json: { detail: 'Бюджет слишком мал.' } } : undefined)
    render(<RecommendPage ai={null} />)
    await submitParams()

    expect(await screen.findByText('Бюджет слишком мал.')).toBeInTheDocument()
  })
})

describe('подбор по описанию', () => {
  it('подставляет пример запроса в поле ввода', async () => {
    mockApi()
    render(<RecommendPage ai={null} />)
    const ask = screen.getByLabelText('Опишите словами')
    const submit = screen.getByRole('button', { name: 'Подобрать по описанию' })
    expect(submit).toBeDisabled()

    await userEvent.click(screen.getByRole('button', { name: 'Для учёбы и офиса, бюджет 45 000' }))

    expect(ask).toHaveValue('Для учёбы и офиса, бюджет 45 000')
    expect(submit).toBeEnabled()
  })

  it('разбирает описание, переносит параметры в форму и подбирает сборки', async () => {
    const parsed: RecommendParams = {
      budget: 180_000, scenario: 'workstation', resolution: '1440p', platform: 'intel', cpu_id: null, gpu_id: null,
    }
    const fetchMock = mockApi((path) => {
      if (path === '/api/ai/parse') return { json: { params: parsed, source: 'rules', notes: 'Понял: монтаж, 180 000 ₽.' } }
      if (path === '/api/recommend') return { json: recommendResult }
    })
    render(<RecommendPage ai={null} />)

    await userEvent.type(screen.getByLabelText('Опишите словами'), 'монтаж за 180к на интеле')
    await userEvent.click(screen.getByRole('button', { name: 'Подобрать по описанию' }))

    expect(requestsTo(fetchMock, '/api/ai/parse')).toEqual([{ text: 'монтаж за 180к на интеле' }])
    expect(requestsTo(fetchMock, '/api/recommend')).toEqual([parsed])
    expect(screen.getByText('Понял: монтаж, 180 000 ₽.')).toBeInTheDocument()
    expect(screen.getByLabelText('Бюджет в рублях')).toHaveValue(180_000)
    expect(screen.getByRole('radio', { name: 'Intel' })).toHaveAttribute('aria-checked', 'true')
    expect(tiers().getByRole('button', { name: /Оптимальная/ })).toBeInTheDocument()
  })
})
