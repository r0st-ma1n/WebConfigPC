// Кнопка «Поделиться»: сохраняет сборку на сервере и показывает ссылку /b/<код>
import { useState } from 'react'
import { api, ApiError } from '../api'
import type { Recommendation, RecommendParams } from '../types'

type State =
  | { status: 'idle' | 'saving' }
  | { status: 'saved'; url: string; copied: boolean }
  | { status: 'error'; message: string }

/** Ссылка относится к конкретному составу сборки, поэтому родитель задаёт key по деталям:
 *  после замены детали кнопка снова предлагает сохранить, а не показывает старую ссылку. */
export function ShareBuild({ rec, params }: { rec: Recommendation; params: RecommendParams }) {
  const [state, setState] = useState<State>({ status: 'idle' })

  async function save() {
    setState({ status: 'saving' })
    try {
      const { slug } = await api.saveBuild(params, rec.parts.map((p) => p.id), rec.tier)
      setState({ status: 'saved', url: `${window.location.origin}/b/${slug}`, copied: false })
    } catch (e) {
      setState({ status: 'error', message: e instanceof ApiError ? e.message : 'Не удалось сохранить сборку.' })
    }
  }

  async function copy(url: string) {
    try {
      await navigator.clipboard.writeText(url)
      setState({ status: 'saved', url, copied: true })
    } catch {
      // Буфер обмена недоступен (например, страница открыта не по HTTPS) — ссылку можно выделить вручную
    }
  }

  if (state.status === 'saved') {
    return (
      <div className="share-link">
        <input className="input" readOnly value={state.url} aria-label="Ссылка на сборку"
          onFocus={(e) => e.currentTarget.select()} />
        <button type="button" className="btn btn-ghost btn-small" onClick={() => copy(state.url)}>
          {state.copied ? 'Скопировано' : 'Скопировать'}
        </button>
      </div>
    )
  }
  return (
    <div className="share-link">
      <button type="button" className="btn btn-ghost btn-small" disabled={state.status === 'saving'} onClick={save}>
        {state.status === 'saving' ? 'Сохраняю…' : 'Поделиться сборкой'}
      </button>
      {state.status === 'error' && <span className="notice notice-error" role="alert">{state.message}</span>}
    </div>
  )
}
