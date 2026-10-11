// Замены деталей: «Доплатить» и «Сэкономить». Каждую можно применить одним нажатием.
import { CATEGORY_TITLES, rub, rubDelta } from '../format'
import type { Alternative, Component } from '../types'

interface Props {
  upgrades: Alternative[]
  savings: Alternative[]
  parts: Component[]
  busy: boolean
  onApply: (alt: Alternative) => void
}

function scenarioEffect(alt: Alternative) {
  const pct = alt.score_delta_pct
  if (Math.abs(pct) < 0.5) return <span className="muted">без заметной разницы</span>
  return (
    <span className={pct > 0 ? 'delta-up' : 'delta-down'}>
      {pct > 0 ? '+' : '−'}{Math.abs(pct).toFixed(0)}% производительности
    </span>
  )
}

function AltItem({ alt, parts, busy, onApply }: { alt: Alternative; parts: Component[]; busy: boolean; onApply: () => void }) {
  const old = parts.find((p) => p.category === alt.category)
  return (
    <li className="alt">
      <div className="alt-top">
        <span className="alt-name">{alt.new_part.title}</span>
        <span className="num">{rub(alt.new_part.price_rub)}</span>
      </div>
      <div className="alt-instead">
        {CATEGORY_TITLES[alt.category]}{old ? ` вместо ${old.title}` : ''}
        {/* Вынужденные изменения: например, другая плата при смене сокета или кулер для процессора без боксового */}
        {alt.also_changed.length > 0 &&
          `. Потребуется также: ${alt.also_changed.map((p) => `${CATEGORY_TITLES[p.category].toLowerCase()} ${p.title}`).join(', ')}`}
      </div>
      <div className="alt-effect">
        <span className="num">{rubDelta(alt.price_delta)}</span>
        {scenarioEffect(alt)}
        {alt.kind === 'upgrade' && !alt.worth_it && <span className="tag">мало пользы за эти деньги</span>}
        <button type="button" className="btn btn-ghost btn-small" disabled={busy} onClick={onApply}>
          Применить
        </button>
      </div>
    </li>
  )
}

export function Alternatives({ upgrades, savings, parts, busy, onApply }: Props) {
  return (
    <div className="alts">
      <section>
        <h3>Что даст доплата</h3>
        {upgrades.length === 0 ? (
          <p className="muted">Доплата за отдельные детали здесь почти ничего не даст.</p>
        ) : (
          <ul className="alt-list">
            {upgrades.map((a) => <AltItem key={a.new_part.id} alt={a} parts={parts} busy={busy} onApply={() => onApply(a)} />)}
          </ul>
        )}
      </section>
      <section>
        <h3>Где сэкономить</h3>
        {savings.length === 0 ? (
          <p className="muted">Сэкономить без заметной потери не получится: всё подобрано впритык.</p>
        ) : (
          <ul className="alt-list">
            {savings.map((a) => <AltItem key={a.new_part.id} alt={a} parts={parts} busy={busy} onApply={() => onApply(a)} />)}
          </ul>
        )}
      </section>
    </div>
  )
}
