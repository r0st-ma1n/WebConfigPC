// Кнопка «Поделиться»: сохраняет сборку на сервере и показывает ссылку /b/<код>
import { useState } from 'react'
import { api, ApiError } from '../api'
import { useAuth } from '../auth'
import { Link } from '../router'
import type { Recommendation, RecommendParams } from '../types'

type State =
  | { status: 'idle' | 'saving' }
  // inAccount: при сохранении пользователь был вошедшим, и сборка попала в «Мои сборки»
  | { status: 'saved'; url: string; copied: boolean; inAccount: boolean }
  | { status: 'error'; message: string }

/** Ссылка относится к конкретному составу сборки, поэтому родитель задаёт key по деталям:
 *  после замены детали кнопка снова предлагает сохранить, а не показывает старую ссылку. */
export function ShareBuild({ rec, params }: { rec: Recommendation; params: RecommendParams }) {
  const [state, setState] = useState<State>({ status: 'idle' })
  const { user } = useAuth()

  async function save() {
    setState({ status: 'saving' })
    try {
      const { slug } = await api.saveBuild(params, rec.parts.map((p) => p.id), rec.tier)
      setState({ status: 'saved', url: `${window.location.origin}/b/${slug}`, copied: false, inAccount: !!user })
    } catch (e) {
      setState({ status: 'error', message: e instanceof ApiError ? e.message : 'Не удалось сохранить сборку.' })
    }
  }

  async function copy(url: string, inAccount: boolean) {
    try {
      await navigator.clipboard.writeText(url)
      setState({ status: 'saved', url, copied: true, inAccount })
    } catch {
      // Буфер обмена недоступен (например, страница открыта не по HTTPS) — ссылку можно выделить вручную
    }
  }

  if (state.status === 'saved') {
    return (
      <div className="share-link">
        <input className="input" readOnly value={state.url} aria-label="Ссылка на сборку"
          onFocus={(e) => e.currentTarget.select()} />
        <button type="button" className="btn btn-ghost btn-small" onClick={() => copy(state.url, state.inAccount)}>
          {state.copied ? 'Скопировано' : 'Скопировать'}
        </button>
        {state.inAccount
          ? <span className="muted share-note">Сборка добавлена в <Link to="/account">«Мои сборки»</Link></span>
          : user
            // Сохранили до входа — у этой копии нет владельца, предлагаем сохранить ещё раз уже в аккаунт
            ? <button type="button" className="link-btn share-note" onClick={save}>Сохранить в «Мои сборки»</button>
            : <span className="muted share-note"><Link to="/login">Войдите</Link>, чтобы сборки сохранялись в аккаунт</span>}
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
