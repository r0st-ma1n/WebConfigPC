import { CATEGORIES, CATEGORY_TITLES, keySpecs, rub } from '../format'
import type { Component } from '../types'
import { useState } from 'react'

export function PartsList({ parts }: { parts: Component[] }) {
  const [expanded, setExpanded] = useState<number[]>([])
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
          <button className="part-expand" type="button" aria-expanded={expanded.includes(p.id)} onClick={() => setExpanded((ids) => ids.includes(p.id) ? ids.filter((id) => id !== p.id) : [...ids, p.id])}>
            <span className="part-title">{p.title}</span>
            <span className="part-specs">{expanded.includes(p.id) ? 'Скрыть характеристики' : keySpecs(p)}</span>
            {expanded.includes(p.id) && <span className="part-extra">{Object.entries(p.specs).map(([key, value]) => <span key={key}><b>{key.replaceAll('_', ' ')}</b> {String(value)}</span>)}</span>}
          </button>
          <span className="part-price num">{rub(p.price_rub)}</span>
        </li>
      ))}
    </ul>
  )
}
