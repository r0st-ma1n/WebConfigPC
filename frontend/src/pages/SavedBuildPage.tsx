// Сохранённая сборка по ссылке /b/<код>: оценка по текущим ценам и изменение цены с момента сохранения
import { useEffect, useState } from 'react'
import { api, ApiError } from '../api'
import { BuildDetails } from '../components/BuildDetails'
import { rub, rubDelta, SCENARIO_TITLES } from '../format'
import { Link } from '../router'
import type { AiStatus, Alternative, Recommendation, SavedBuild } from '../types'

const dateFormat = new Intl.DateTimeFormat('ru-RU', { day: 'numeric', month: 'long', year: 'numeric' })

export function SavedBuildPage({ slug, ai }: { slug: string; ai: AiStatus | null }) {
  const [saved, setSaved] = useState<SavedBuild | null>(null)
  // Текущая сборка: сохранённая или она же после применённых замен
  const [rec, setRec] = useState<Recommendation | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    // Состояние при смене ссылки сбрасывает App: страница монтируется заново с key по адресу
    let cancelled = false
    api.savedBuild(slug)
      .then((s) => { if (!cancelled) { setSaved(s); setRec(s.recommendation) } })
      .catch((e) => { if (!cancelled) setError(e instanceof ApiError ? e.message : 'Не удалось открыть сборку.') })
    return () => { cancelled = true }
  }, [slug])

  async function applyAlternative(alt: Alternative) {
    if (!saved) return
    setBusy(true)
    setError(null)
    try {
      setRec(await api.evaluate(saved.params, alt.part_ids))
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Не удалось применить замену.')
    } finally {
      setBusy(false)
    }
  }

  if (error && !saved) {
    return (
      <div className="saved-page">
        <h1>Сборка не открылась</h1>
        <p className="notice notice-error">{error}</p>
        <Link className="btn btn-primary" to="/recommend">Подобрать сборку</Link>
      </div>
    )
  }
  if (!saved || !rec) return <p className="muted">Загружаю сборку…</p>

  const priceChange = saved.recommendation.total_price - saved.saved_price
  const { params } = saved
  return (
    <div className="saved-page">
      <div className="eyebrow"><span className="eyebrow-line" />СОХРАНЁННАЯ СБОРКА</div>
      <h1>{saved.recommendation.title}</h1>
      <p className="muted">
        Сохранена {dateFormat.format(new Date(saved.created_at))}. {SCENARIO_TITLES[params.scenario]}
        {params.scenario === 'gaming' && `, ${params.resolution}`}, бюджет {rub(params.budget)}.
      </p>
      {priceChange !== 0 && (
        <p className="notice notice-info">
          С момента сохранения цена изменилась: было {rub(saved.saved_price)}, сейчас{' '}
          {rub(saved.recommendation.total_price)} ({rubDelta(priceChange)}).
        </p>
      )}
      {rec !== saved.recommendation && (
        <p className="notice notice-info">
          Это сборка с применёнными заменами.{' '}
          <button type="button" className="link-btn" onClick={() => setRec(saved.recommendation)}>
            Вернуть сохранённую
          </button>
        </p>
      )}
      {error && <p className="notice notice-error">{error}</p>}
      <BuildDetails rec={rec} allocation={null} params={params} aiEnabled={!!ai?.enabled} busy={busy}
        onApply={applyAlternative} />
      <p><Link className="text-link" to="/recommend">Подобрать свою сборку <span>→</span></Link></p>
    </div>
  )
}
