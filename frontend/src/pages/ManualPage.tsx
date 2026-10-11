// Ручная сборка по шагам: на каждом шаге видны только совместимые детали
import { useEffect, useMemo, useState } from 'react'
import { api, ApiError } from '../api'
import { Issues } from '../components/Issues'
import { CATEGORY_TITLES, keySpecs, rub } from '../format'
import type { Category, CheckResult, Component, Option } from '../types'

// Порядок шагов: сначала то, от чего зависят остальные детали
const STEPS: Category[] = ['cpu', 'motherboard', 'ram', 'gpu', 'storage', 'cooler', 'case', 'psu']

type Selection = Partial<Record<Category, Component>>

export function ManualPage() {
  const [selection, setSelection] = useState<Selection>({})
  const [step, setStep] = useState<Category>('cpu')
  // Загруженные варианты запоминаются вместе с ключом запроса (шаг + выбранные детали)
  const [loaded, setLoaded] = useState<{ key: string; options: Option[] } | null>(null)
  const [showIncompatible, setShowIncompatible] = useState(false)
  const [search, setSearch] = useState('')
  const [check, setCheck] = useState<CheckResult | null>(null)
  const [complete, setComplete] = useState(false) // проверить как законченную сборку
  const [error, setError] = useState<string | null>(null)

  const selectedIds = useMemo(() => Object.values(selection).map((p) => p!.id), [selection])

  // Варианты для текущего шага: передаём все выбранные детали, кроме детали этого шага
  const otherIds = Object.entries(selection).filter(([c]) => c !== step).map(([, p]) => p!.id)
  const optionsKey = `${step}:${otherIds.join(',')}`
  const options = loaded?.key === optionsKey ? loaded.options : null

  useEffect(() => {
    let cancelled = false
    const [category, ids] = optionsKey.split(':') as [Category, string]
    api.options(ids ? ids.split(',').map(Number) : [], category)
      .then((o) => !cancelled && setLoaded({ key: optionsKey, options: o }))
      .catch((e) => !cancelled && setError(e instanceof ApiError ? e.message : 'Не удалось загрузить варианты.'))
    return () => { cancelled = true }
  }, [optionsKey])

  // Проверка совместимости и итоговая цена при каждом изменении сборки
  useEffect(() => {
    let cancelled = false
    api.check(selectedIds, complete, '1440p')
      .then((r) => !cancelled && setCheck(r))
      .catch(() => {})
    return () => { cancelled = true }
  }, [selectedIds, complete])

  function choose(part: Component) {
    const isSame = selection[step]?.id === part.id
    setSelection((s) => {
      const next = { ...s }
      if (isSame) delete next[step]
      else next[step] = part
      return next
    })
    if (!isSame) {
      // Переходим к следующему ещё не выбранному шагу
      const nextStep = STEPS.find((c) => c !== step && !selection[c])
      if (nextStep) setStep(nextStep)
    }
  }

  const cpu = selection.cpu?.specs as Record<string, unknown> | undefined
  const optionalHint: Partial<Record<Category, string>> = {
    gpu: cpu?.has_igpu ? 'У процессора есть встроенная графика — видеокарту можно не ставить.' : undefined,
    cooler: cpu?.includes_cooler ? 'Кулер идёт в комплекте с процессором — этот шаг можно пропустить.' : undefined,
  }

  const query = search.trim().toLowerCase()
  const visible = (options ?? [])
    .filter((o) => showIncompatible || o.compatible)
    .filter((o) => !query || o.component.title.toLowerCase().includes(query))
  const hiddenCount = (options ?? []).filter((o) => !o.compatible).length

  return (
    <>
      <h1>Соберите компьютер сами</h1>
      <p className="lead">
        Выбирайте детали по шагам. На каждом шаге показаны только те, что подходят к уже выбранным,
        а справа — итоговая цена и предупреждения.
      </p>

      <div className="manual-layout">
        <nav aria-label="Шаги сборки">
          <ol className="steps">
            {STEPS.map((c, i) => (
              <li key={c}>
                <button
                  type="button"
                  className={`step${selection[c] ? ' done' : ''}`}
                  aria-current={step === c ? 'step' : undefined}
                  onClick={() => setStep(c)}
                >
                  <span className="step-num">{i + 1}</span>
                  <span className="step-title">{CATEGORY_TITLES[c]}</span>
                  <span className="step-choice">{selection[c]?.title ?? 'не выбрано'}</span>
                </button>
              </li>
            ))}
          </ol>
        </nav>

        <section className="panel">
          <div className="options-head">
            <h2>{CATEGORY_TITLES[step]}</h2>
            <input
              className="input"
              style={{ maxWidth: 240 }}
              type="search"
              placeholder="Поиск по названию"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              aria-label="Поиск по названию"
            />
          </div>
          {optionalHint[step] && <p className="notice notice-info" style={{ marginTop: 0 }}>{optionalHint[step]}</p>}
          {error && <p className="notice notice-error">{error}</p>}

          {options === null ? (
            <p className="loading">Загружаю варианты…</p>
          ) : (
            <>
              <ul className="options">
                {visible.map(({ component: p, compatible, reasons }) => (
                  <li key={p.id}>
                    <button
                      type="button"
                      className="option"
                      aria-pressed={selection[step]?.id === p.id}
                      disabled={!compatible}
                      onClick={() => choose(p)}
                    >
                      <span>
                        <span className="part-title">{p.title}</span>
                        <span className="part-specs" style={{ display: 'block' }}>{keySpecs(p)}</span>
                      </span>
                      <span className="part-price num">{rub(p.price_rub)}</span>
                      {!compatible && <span className="option-reason">{reasons[0]}</span>}
                    </button>
                  </li>
                ))}
              </ul>
              {visible.length === 0 && <p className="muted">Ничего не найдено. Измените поиск или выбранные детали.</p>}
              {hiddenCount > 0 && (
                <label className="check" style={{ marginTop: 14 }}>
                  <input type="checkbox" checked={showIncompatible} onChange={(e) => setShowIncompatible(e.target.checked)} />
                  Показать несовместимые ({hiddenCount}) и причины
                </label>
              )}
            </>
          )}
        </section>

        <aside className="panel summary" aria-live="polite">
          <div>
            <div className="muted" style={{ fontSize: 14 }}>Итого</div>
            <div className="summary-total num">{rub(check?.total_price ?? 0)}</div>
          </div>
          <dl>
            <dt>Выбрано деталей</dt>
            <dd className="num">{selectedIds.length} из {STEPS.length}</dd>
            <dt>Потребление</dt>
            <dd className="num">≈ {check?.estimated_power_w ?? 0} Вт</dd>
            <dt>Рекомендуемый БП</dt>
            <dd className="num">от {check?.recommended_psu_w ?? 0} Вт</dd>
          </dl>
          <label className="check">
            <input type="checkbox" checked={complete} onChange={(e) => setComplete(e.target.checked)} />
            Проверить как готовую сборку
          </label>
          {check && check.issues.length > 0 && <Issues issues={check.issues} />}
          {check && check.issues.length === 0 && selectedIds.length > 0 && (
            <p className="notice notice-info" style={{ margin: 0 }}>
              {complete ? 'Сборка готова: всё совместимо.' : 'Пока всё совместимо.'}
            </p>
          )}
          {selectedIds.length > 0 && (
            <button type="button" className="btn btn-ghost" onClick={() => { setSelection({}); setStep('cpu') }}>
              Начать заново
            </button>
          )}
        </aside>
      </div>
    </>
  )
}
