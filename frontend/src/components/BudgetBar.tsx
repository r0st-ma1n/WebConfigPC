// Полоса бюджета: как алгоритм планировал распределить деньги и куда они реально ушли.
// Цвета категорий фиксированы (см. --c-* в index.css), подписи и суммы — в таблице под полосами.
import { CATEGORIES, CATEGORY_TITLES, rub } from '../format'
import type { Category, Component } from '../types'

interface Props {
  allocation: Record<Category, number> | null // плановое распределение (нет для своей сборки)
  parts: Component[]
}

function Bar({ label, values }: { label: string; values: Record<Category, number> }) {
  const total = CATEGORIES.reduce((sum, c) => sum + values[c], 0)
  return (
    <div className="bar-row">
      <span className="bar-label">{label}</span>
      <div className="bar" role="img" aria-label={`${label}: распределение по категориям`}>
        {CATEGORIES.filter((c) => values[c] > 0).map((c, i) => (
          <div
            key={c}
            className="bar-seg"
            title={`${CATEGORY_TITLES[c]}: ${rub(values[c])} (${Math.round((values[c] / total) * 100)}%)`}
            style={{
              width: `${(values[c] / total) * 100}%`,
              background: `var(--c-${c})`,
              animationDelay: `${i * 40}ms`,
            }}
          />
        ))}
      </div>
    </div>
  )
}

export function BudgetBar({ allocation, parts }: Props) {
  const spent = Object.fromEntries(CATEGORIES.map((c) => [c, 0])) as Record<Category, number>
  for (const p of parts) spent[p.category] += p.price_rub
  const total = parts.reduce((sum, p) => sum + p.price_rub, 0)

  return (
    <div className="budget-bars">
      {allocation && <Bar label="План" values={allocation} />}
      <Bar label="Сборка" values={spent} />
      <table className="budget-legend">
        <thead>
          <tr>
            <th>Категория</th>
            {allocation && <th>План</th>}
            <th>Потрачено</th>
            <th>Доля</th>
          </tr>
        </thead>
        <tbody>
          {CATEGORIES.filter((c) => spent[c] > 0 || (allocation && allocation[c] > 0)).map((c) => (
            <tr key={c}>
              <td>
                <span className="swatch" style={{ background: `var(--c-${c})` }} />
                {CATEGORY_TITLES[c]}
              </td>
              {allocation && <td className="num muted">{rub(allocation[c])}</td>}
              <td className="num">{spent[c] ? rub(spent[c]) : '—'}</td>
              <td className="num muted">{Math.round((spent[c] / total) * 100)}%</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
