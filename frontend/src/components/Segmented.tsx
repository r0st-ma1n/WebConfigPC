// Переключатель «один из нескольких» (радиогруппа в виде кнопок)
interface Props<T extends string> {
  label: string
  value: T
  options: { value: T; title: string }[]
  onChange: (value: T) => void
}

export function Segmented<T extends string>({ label, value, options, onChange }: Props<T>) {
  return (
    <div className="segmented" role="radiogroup" aria-label={label}>
      {options.map((o) => (
        <button
          key={o.value}
          type="button"
          role="radio"
          aria-checked={o.value === value}
          onClick={() => onChange(o.value)}
        >
          {o.title}
        </button>
      ))}
    </div>
  )
}
