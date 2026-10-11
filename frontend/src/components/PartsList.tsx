import { CATEGORIES, CATEGORY_TITLES, keySpecs, rub } from '../format'
import type { Component } from '../types'

export function PartsList({ parts }: { parts: Component[] }) {
  // Показываем детали в привычном порядке категорий, а не в порядке ответа сервера
  const sorted = [...parts].sort((a, b) => CATEGORIES.indexOf(a.category) - CATEGORIES.indexOf(b.category))
  return (
    <ul className="parts">
      {sorted.map((p) => (
        <li className="part" key={p.id}>
          <span className="part-cat">
            <span className="swatch" style={{ background: `var(--c-${p.category})` }} />
            {CATEGORY_TITLES[p.category]}
          </span>
          <div>
            <div className="part-title">{p.title}</div>
            <div className="part-specs">{keySpecs(p)}</div>
          </div>
          <span className="part-price num">{rub(p.price_rub)}</span>
        </li>
      ))}
    </ul>
  )
}
