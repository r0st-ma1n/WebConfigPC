import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { cpu, gpu, recommendation } from '../test/fixtures'
import type { RecommendParams } from '../types'
import { BuildDetails } from './BuildDetails'

const rec = recommendation('optimal', 'Оптимальная', [cpu, gpu], 75)

// У каждого теста свой бюджет: готовые объяснения кэшируются по параметрам подбора
const params = (budget: number): RecommendParams => ({
  budget, scenario: 'gaming', resolution: '1440p', platform: null, cpu_id: null, gpu_id: null,
})

/** Ответ потока объяснения: NDJSON, нарезанный на куски не по границам строк */
function mockStream(chunks: string[]) {
  return vi.spyOn(globalThis, 'fetch').mockImplementation(async () => new Response(
    new ReadableStream({
      start(controller) {
        for (const chunk of chunks) controller.enqueue(new TextEncoder().encode(chunk))
        controller.close()
      },
    }),
  ))
}

const renderDetails = (budget: number, aiEnabled = true) => render(
  <BuildDetails rec={rec} allocation={null} params={params(budget)} aiEnabled={aiEnabled} busy={false} onApply={() => {}} />,
)

describe('объяснение сборки', () => {
  it('без ИИ показывает шаблонное объяснение и не обращается к серверу', () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch')
    renderDetails(100_000, false)

    expect(screen.getByText('Объяснение сборки «Оптимальная».')).toBeInTheDocument()
    expect(screen.getByText('Объяснение составлено по данным алгоритма подбора.')).toBeInTheDocument()
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('собирает текст модели из потока, даже если события пришли разрезанными', async () => {
    mockStream(['{"delta":"Процессор ', 'подобран под игры."}\n{"del', 'ta":" Видеокарта тянет 2K."}\n', '{"done":true,"source":"llm"}\n'])
    renderDetails(110_000)

    expect(await screen.findByText('Объяснение написал ИИ по данным алгоритма подбора.')).toBeInTheDocument()
    expect(screen.getByText('Процессор подобран под игры. Видеокарта тянет 2K.')).toBeInTheDocument()
  })

  it('возвращается к шаблону, если сервер переключился на него посреди ответа', async () => {
    mockStream(['{"delta":"Оборванный текст"}\n', '{"done":true,"source":"template"}\n'])
    renderDetails(120_000)

    expect(await screen.findByText('Объяснение составлено по данным алгоритма подбора.')).toBeInTheDocument()
    expect(screen.getByText('Объяснение сборки «Оптимальная».')).toBeInTheDocument()
    expect(screen.queryByText('Оборванный текст')).not.toBeInTheDocument()
  })

  it('возвращается к шаблону, если поток закрылся без финального события', async () => {
    mockStream(['{"delta":"Неполный ответ"}\n'])
    renderDetails(130_000)

    expect(await screen.findByText('Объяснение составлено по данным алгоритма подбора.')).toBeInTheDocument()
    expect(screen.queryByText('Неполный ответ')).not.toBeInTheDocument()
  })
})
