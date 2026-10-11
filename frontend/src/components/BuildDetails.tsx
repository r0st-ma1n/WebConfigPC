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

/** Сначала показываем шаблонное объяснение, а если подключён ИИ — заменяем его текстом модели. */
function useExplanation(rec: Recommendation, params: RecommendParams, aiEnabled: boolean): Explanation {
  // Ответ модели запоминается вместе со сборкой, к которой он относится
  const [llm, setLlm] = useState<{ rec: Recommendation; text: string | null } | null>(null)

  useEffect(() => {
    if (!aiEnabled) return
    let cancelled = false // ответ мог прийти, когда пользователь уже выбрал другую сборку
    api.explain(params, rec.parts.map((p) => p.id), rec.tier)
      .then((r) => !cancelled && setLlm({ rec, text: r.source === 'llm' ? r.text : null }))
      .catch(() => !cancelled && setLlm({ rec, text: null }))
    return () => { cancelled = true }
  }, [rec, params, aiEnabled])

  const ready = llm?.rec === rec
  if (ready && llm.text) return { text: llm.text, source: 'llm', loading: false }
  return { text: rec.explanation, source: 'template', loading: aiEnabled && !ready }
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
            ? 'ИИ готовит объяснение простыми словами…'
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
