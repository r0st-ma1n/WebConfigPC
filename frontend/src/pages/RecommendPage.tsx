// Подбор: запрос словами или параметрами -> 2–3 сборки с объяснением и заменами
import { useEffect, useRef, useState } from 'react'
import { api, ApiError } from '../api'
import { BuildDetails } from '../components/BuildDetails'
import { Segmented } from '../components/Segmented'
import { rub, SCENARIO_TITLES } from '../format'
import type {
  Alternative, AiStatus, Component, Platform, Recommendation, RecommendParams, RecommendResult, Resolution, Scenario,
} from '../types'
import { EXAMPLES, selectExample, updateRecommendParams } from '../recommendation-form.js'

const DEFAULT_PARAMS: RecommendParams = {
  budget: 100_000, scenario: 'gaming', resolution: '1440p', platform: null, cpu_id: null, gpu_id: null,
}
const BUDGET_MIN = 30_000
const BUDGET_MAX = 400_000

export function RecommendPage({ ai }: { ai: AiStatus | null }) {
  const [params, setParams] = useState<RecommendParams>(DEFAULT_PARAMS)
  const [text, setText] = useState('')
  const [parseNotes, setParseNotes] = useState<string | null>(null)

  const [result, setResult] = useState<RecommendResult | null>(null)
  const [usedParams, setUsedParams] = useState<RecommendParams>(DEFAULT_PARAMS) // параметры показанного подбора
  const [selected, setSelected] = useState(0) // индекс варианта или -1 для «Вашей сборки»
  const [custom, setCustom] = useState<Recommendation | null>(null) // сборка после применения замены

  const [loading, setLoading] = useState<'parse' | 'recommend' | 'apply' | null>(null)
  const [error, setError] = useState<string | null>(null)

  // Списки процессоров и видеокарт для необязательного выбора конкретной модели
  const [cpus, setCpus] = useState<Component[]>([])
  const [gpus, setGpus] = useState<Component[]>([])
  useEffect(() => {
    api.components('cpu').then(setCpus).catch(() => {})
    api.components('gpu').then(setGpus).catch(() => {})
  }, [])

  // На узком экране результаты оказываются под формой — после подбора прокручиваем к ним
  const resultsRef = useRef<HTMLElement>(null)
  const scrollToResults = () => {
    if (window.matchMedia('(max-width: 900px)').matches) {
      setTimeout(() => resultsRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' }), 50)
    }
  }

  const update = (patch: Partial<RecommendParams>) => setParams((p) => updateRecommendParams(p, patch))

  async function runRecommend(p: RecommendParams) {
    setLoading('recommend')
    setError(null)
    try {
      const r = await api.recommend(p)
      setResult(r)
      setUsedParams(p)
      setCustom(null)
      // По умолчанию открываем «Оптимальную»
      setSelected(Math.max(0, r.recommendations.findIndex((x) => x.tier === 'optimal')))
      scrollToResults()
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Не удалось подобрать сборку.')
    } finally {
      setLoading(null)
    }
  }

  async function runParse() {
    if (text.trim().length < 3) return
    setLoading('parse')
    setError(null)
    try {
      const r = await api.parse(text)
      setParseNotes(r.notes)
      if (r.params) {
        setParams(r.params)
        await runRecommend(r.params)
      }
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Не удалось разобрать запрос.')
    } finally {
      setLoading((l) => (l === 'parse' ? null : l))
    }
  }

  async function applyAlternative(alt: Alternative) {
    setLoading('apply')
    setError(null)
    try {
      setCustom(await api.evaluate(usedParams, alt.part_ids))
      setSelected(-1)
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Не удалось применить замену.')
    } finally {
      setLoading(null)
    }
  }

  const recs = result?.recommendations ?? []
  const current = selected === -1 ? custom : recs[selected]

  return (
    <>
      <h1>Подберём компьютер под ваши задачи</h1>
      <p className="lead">
        Опишите, для чего нужен компьютер и сколько вы готовы потратить. Система предложит несколько
        совместимых сборок, объяснит выбор и подскажет, где доплатить, а где сэкономить.
      </p>

      <div className="recommend-layout">
        <aside className="panel form-panel">
          <form className="ask" onSubmit={(e) => { e.preventDefault(); runParse() }}>
            <label className="field-label" htmlFor="ask">Опишите словами</label>
            <textarea
              id="ask"
              className="textarea"
              placeholder={EXAMPLES[0]}
              value={text}
              onChange={(e) => setText(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) runParse() }}
            />
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '4px 12px', fontSize: 13 }}>
              {EXAMPLES.slice(1).map((ex) => (
                <button key={ex} type="button" className="link-btn" onClick={() => setText(selectExample(ex))}>{ex}</button>
              ))}
            </div>
            <button className="btn btn-primary" disabled={loading !== null || text.trim().length < 3}>
              {loading === 'parse' ? 'Разбираю запрос…' : 'Подобрать по описанию'}
            </button>
            {parseNotes && <p className="notice notice-info ask-notes" style={{ margin: 0 }}>{parseNotes}</p>}
          </form>

          <div className="divider-text">или задайте параметры</div>

          <form style={{ display: 'grid', gap: 18 }} onSubmit={(e) => { e.preventDefault(); runRecommend(params) }}>
            <div className="field">
              <div className="budget-row">
                <label htmlFor="budget">Бюджет</label>
                <input
                  className="input budget-input num"
                  type="number"
                  min={10_000}
                  step={1_000}
                  value={params.budget}
                  onChange={(e) => update({ budget: Number(e.target.value) })}
                  aria-label="Бюджет в рублях"
                />
              </div>
              <input
                id="budget"
                className="range"
                type="range"
                min={BUDGET_MIN}
                max={BUDGET_MAX}
                step={5_000}
                value={Math.min(Math.max(params.budget, BUDGET_MIN), BUDGET_MAX)}
                onChange={(e) => update({ budget: Number(e.target.value) })}
              />
              <div className="budget-value num">{rub(params.budget)}</div>
            </div>

            <div className="field">
              <span className="field-label">Для чего компьютер</span>
              <Segmented<Scenario>
                label="Сценарий"
                value={params.scenario}
                options={(Object.keys(SCENARIO_TITLES) as Scenario[]).map((s) => ({ value: s, title: SCENARIO_TITLES[s] }))}
                onChange={(scenario) => update({ scenario })}
              />
            </div>

            {params.scenario === 'gaming' && (
              <div className="field">
                <span className="field-label">Разрешение монитора</span>
                <Segmented<Resolution>
                  label="Разрешение"
                  value={params.resolution}
                  options={[
                    { value: '1080p', title: 'Full HD' },
                    { value: '1440p', title: '2K' },
                    { value: '4k', title: '4K' },
                  ]}
                  onChange={(resolution) => update({ resolution })}
                />
              </div>
            )}

            <details className="more">
              <summary>Пожелания к комплектующим</summary>
              <div className="field">
                <span className="field-label">Платформа</span>
                <Segmented<'any' | Platform>
                  label="Платформа"
                  value={params.platform ?? 'any'}
                  options={[
                    { value: 'any', title: 'Любая' },
                    { value: 'amd', title: 'AMD' },
                    { value: 'intel', title: 'Intel' },
                  ]}
                  onChange={(v) => update({ platform: v === 'any' ? null : v })}
                />
              </div>
              <div className="field">
                <label htmlFor="cpu">Конкретный процессор</label>
                <select id="cpu" className="select" value={params.cpu_id ?? ''}
                  onChange={(e) => update({ cpu_id: e.target.value ? Number(e.target.value) : null })}>
                  <option value="">Подобрать автоматически</option>
                  {cpus.map((c) => <option key={c.id} value={c.id}>{c.title} — {rub(c.price_rub)}</option>)}
                </select>
              </div>
              <div className="field">
                <label htmlFor="gpu">Конкретная видеокарта</label>
                <select id="gpu" className="select" value={params.gpu_id ?? ''}
                  onChange={(e) => update({ gpu_id: e.target.value ? Number(e.target.value) : null })}>
                  <option value="">Подобрать автоматически</option>
                  {gpus.map((g) => <option key={g.id} value={g.id}>{g.title} — {rub(g.price_rub)}</option>)}
                </select>
              </div>
            </details>

            <button className="btn btn-primary" disabled={loading !== null}>
              {loading === 'recommend' ? 'Подбираю…' : 'Подобрать сборки'}
            </button>
          </form>
          {ai && !ai.enabled && (
            <p className="muted" style={{ fontSize: 13, margin: 0 }}>
              ИИ не подключён: описание разбирается по ключевым словам, объяснения составляются по шаблону.
            </p>
          )}
        </aside>

        <main ref={resultsRef}>
          {error && <p className="notice notice-error" style={{ marginTop: 0 }}>{error}</p>}

          {!result && !error && (
            <section className="panel empty-state">
              <h2>Здесь появятся сборки</h2>
              <p className="muted" style={{ margin: 0 }}>Для каждого запроса система:</p>
              <ol className="empty-steps">
                <li>делит бюджет между комплектующими с учётом ваших задач;</li>
                <li>перебирает сочетания процессора и видеокарты и проверяет совместимость каждой детали;</li>
                <li>выбирает лучшие по производительности за свои деньги — дешевле, оптимальную и с запасом;</li>
                <li>объясняет выбор и показывает, какие замены имеют смысл.</li>
              </ol>
            </section>
          )}

          {loading === 'recommend' && <section className="panel result-skeleton" aria-label="Подбираем конфигурацию" aria-busy="true"><span/><span/><span/><span/><span/><span/></section>}

          {result && current && loading !== 'recommend' && (
            <div className="results">
              <div className="tiers" role="group" aria-label="Варианты сборки">
                {recs.map((r, i) => (
                  <button key={r.tier} type="button" className="tier" aria-pressed={selected === i} onClick={() => setSelected(i)}>
                    <span className="tier-name">{r.title}</span>
                    <span className="tier-price num">{rub(r.total_price)}</span>
                    <span className="tier-meta">Оценка {r.score.toFixed(0)} из 100</span>
                  </button>
                ))}
                {custom && (
                  <button type="button" className="tier" aria-pressed={selected === -1} onClick={() => setSelected(-1)}>
                    <span className="tier-name">Ваша сборка</span>
                    <span className="tier-price num">{rub(custom.total_price)}</span>
                    <span className="tier-meta">Оценка {custom.score.toFixed(0)} из 100</span>
                  </button>
                )}
              </div>

              {selected === -1 && (
                <p className="notice notice-info applied-bar" style={{ margin: 0 }}>
                  <span>Это сборка с применёнными заменами. Можно продолжить менять детали.</span>
                  <button type="button" className="link-btn" onClick={() => {
                    setCustom(null)
                    setSelected(Math.max(0, recs.findIndex((x) => x.tier === 'optimal')))
                  }}>
                    Сбросить замены
                  </button>
                </p>
              )}

              <BuildDetails
                rec={current}
                allocation={selected === -1 ? null : result.allocation}
                params={usedParams}
                aiEnabled={!!ai?.enabled}
                busy={loading !== null}
                onApply={applyAlternative}
              />
            </div>
          )}
        </main>
      </div>
    </>
  )
}
