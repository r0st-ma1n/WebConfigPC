// Подробности одной сборки: цена, распределение бюджета, состав, объяснение, замены
import { useEffect, useState } from 'react'
import { api } from '../api'
import { rub } from '../format'
import type { Alternative, Category, Recommendation, RecommendParams } from '../types'
import { Alternatives } from './Alternatives'
import { BudgetBar } from './BudgetBar'
import { Issues } from './Issues'
import { PartsList } from './PartsList'

interface Props {
  rec: Recommendation
  allocation: Record<Category, number> | null
  params: RecommendParams
  aiEnabled: boolean
  busy: boolean
  onApply: (alt: Alternative) => void
}

type Explanation = { text: string; source: 'llm' | 'template'; loading: boolean }

// Готовые объяснения модели: при возврате к уже открытой сборке текст не генерируется заново.
// Объяснение зависит и от параметров подбора, и от состава сборки — всё это входит в ключ
const explained = new Map<string, string>()
const CACHE_LIMIT = 50

function remember(key: string, text: string) {
  if (explained.size >= CACHE_LIMIT) explained.delete(explained.keys().next().value!) // самый старый
  explained.set(key, text)
}

/** Сначала показываем шаблонное объяснение, а если подключён ИИ — заменяем его текстом модели,
 *  который дописывается по мере генерации. */
function useExplanation(rec: Recommendation, params: RecommendParams, aiEnabled: boolean): Explanation {
  const key = JSON.stringify([params, rec.parts.map((p) => p.id), rec.tier])
  // Текст модели запоминается вместе со сборкой, к которой он относится.
  // Пустой text — модель не справилась (или ещё не начала), показываем шаблон
  const [llm, setLlm] = useState<{ key: string; text: string; done: boolean } | null>(null)

  useEffect(() => {
    if (!aiEnabled || explained.has(key)) return
    // Пользователь мог выбрать другую сборку — тогда поток для старой обрывается
    // (сервер в ответ останавливает генерацию)
    const controller = new AbortController()
    let text = ''
    let done = false
    const show = () => setLlm({ key, text, done })
    const fail = () => { text = ''; done = true; show() }

    api.explainStream(params, rec.parts.map((p) => p.id), rec.tier, (e) => {
      if ('delta' in e) text += e.delta
      else if (e.source === 'llm') { done = true; remember(key, text) }
      else return fail() // сервер перешёл на шаблон — оборванный текст модели не показываем
      show()
    }, controller.signal)
      // Поток закрылся без финального события — ответ неполный
      .then(() => { if (!done) fail() })
      .catch(() => { if (!controller.signal.aborted) fail() })
    return () => controller.abort()
  }, [key, rec, params, aiEnabled])

  const cached = aiEnabled ? explained.get(key) : undefined
  if (cached) return { text: cached.trimStart(), source: 'llm', loading: false }
  const current = llm?.key === key ? llm : null
  if (current?.text) return { text: current.text.trimStart(), source: 'llm', loading: !current.done }
  return { text: rec.explanation, source: 'template', loading: aiEnabled && !current?.done }
}

export function BuildDetails({ rec, allocation, params, aiEnabled, busy, onApply }: Props) {
  const explanation = useExplanation(rec, params, aiEnabled)
  const { check } = rec
  const overBudget = rec.total_price - params.budget

  return (
    <div className="results">
      <section className="panel">
        <div className="build-head">
          <div>
            <h2>{rec.title}</h2>
            <div className="build-stats">
              <span>Оценка для ваших задач: <strong className="num">{rec.score.toFixed(0)}</strong> из 100</span>
              <span>Потребление ≈ <span className="num">{check.estimated_power_w}</span> Вт</span>
              {overBudget > 0 && <span>Выше бюджета на <span className="num">{rub(overBudget)}</span></span>}
            </div>
          </div>
          <div className="build-total num">{rub(rec.total_price)}</div>
        </div>
      </section>

      <section className="panel">
        <h2 style={{ marginBottom: 8 }}>Состав</h2>
        <PartsList parts={rec.parts} />
      </section>

      <section className="panel explanation" aria-live="polite">
        <h2 style={{ marginBottom: 12 }}>Почему эта сборка</h2>
        {explanation.text.split('\n\n').map((p, i) => <p key={i}>{p}</p>)}
        <p className="source-note">
          {explanation.loading
            ? explanation.source === 'llm'
              ? 'ИИ пишет объяснение…'
              : 'ИИ готовит объяснение простыми словами…'
            : explanation.source === 'llm'
              ? 'Объяснение написал ИИ по данным алгоритма подбора.'
              : 'Объяснение составлено по данным алгоритма подбора.'}
        </p>
      </section>

      {check.issues.length > 0 && (
        <section className="panel">
          <h2 style={{ marginBottom: 12 }}>На что обратить внимание</h2>
          <Issues issues={check.issues} />
        </section>
      )}

      <section className="panel">
        <h2 style={{ marginBottom: 14 }}>Замены</h2>
        <Alternatives upgrades={rec.upgrades} savings={rec.savings} parts={rec.parts} busy={busy} onApply={onApply} />
      </section>

      <section className="panel">
        <h2>Куда ушли деньги</h2>
        <p className="muted" style={{ margin: '6px 0 16px' }}>
          {allocation
            ? 'План — как бюджет делится между категориями для вашего сценария. Сборка — сколько реально стоят выбранные детали.'
            : 'Сколько стоит каждая категория в этой сборке.'}
        </p>
        <BudgetBar allocation={allocation} parts={rec.parts} />
      </section>
    </div>
  )
}
