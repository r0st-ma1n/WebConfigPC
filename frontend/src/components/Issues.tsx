import type { Issue } from '../types'

// Ошибки и предупреждения совместимости. Цвет дублируется значком и текстом уровня,
// чтобы смысл не передавался только цветом.
export function Issues({ issues }: { issues: Issue[] }) {
  if (issues.length === 0) return null
  return (
    <ul className="issue-list">
      {issues.map((issue, i) => (
        <li key={i} className={`notice notice-${issue.level}`}>
          <span className="issue-icon" aria-hidden="true">{issue.level === 'error' ? '✕' : '!'}</span>
          <span>
            <span className="sr-only">{issue.level === 'error' ? 'Ошибка: ' : 'Предупреждение: '}</span>
            {issue.message}
          </span>
        </li>
      ))}
    </ul>
  )
}
