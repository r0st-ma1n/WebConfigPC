// Личный кабинет: сохранённые сборки пользователя и выход
import { useEffect, useState } from 'react'
import { api, ApiError } from '../api'
import { useAuth } from '../auth'
import { rub, SCENARIO_TITLES } from '../format'
import { Link, useNavigate } from '../router'
import type { SavedBuildSummary } from '../types'

const dateFormat = new Intl.DateTimeFormat('ru-RU', { day: 'numeric', month: 'long', year: 'numeric' })

export function AccountPage() {
  const auth = useAuth()
  if (auth.user === undefined) return <div className="content-page"><p className="muted">Загружаю…</p></div>
  if (auth.user === null) {
    return (
      <div className="content-page auth-page">
        <h1>Мои сборки</h1>
        <p className="lead">Войдите, чтобы видеть сохранённые сборки.</p>
        <Link className="btn btn-primary" to="/login">Войти</Link>
      </div>
    )
  }
  // key: при входе под другим аккаунтом список загружается заново
  return <Account key={auth.user.id} email={auth.user.email} />
}

function Account({ email }: { email: string }) {
  const { logout } = useAuth()
  const navigate = useNavigate()
  const [builds, setBuilds] = useState<SavedBuildSummary[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api.myBuilds().then(setBuilds).catch((e) => setError(e instanceof ApiError ? e.message : 'Не удалось загрузить сборки.'))
  }, [])

  async function remove(slug: string) {
    setError(null)
    try {
      await api.deleteBuild(slug)
      setBuilds((list) => list?.filter((b) => b.slug !== slug) ?? null)
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Не удалось удалить сборку.')
    }
  }

  async function signOut(everywhere: boolean) {
    try {
      await logout(everywhere)
      navigate('/')
    } catch {
      setError('Не удалось выйти. Попробуйте ещё раз.')
    }
  }

  return (
    <div className="content-page account-page">
      <div className="eyebrow"><span className="eyebrow-line" />ЛИЧНЫЙ КАБИНЕТ</div>
      <h1>Мои сборки</h1>
      <p className="lead">{email}</p>
      {error && <p className="notice notice-error" role="alert">{error}</p>}

      {builds === null && !error && <p className="muted">Загружаю сборки…</p>}
      {builds?.length === 0 && (
        <section className="panel">
          <p style={{ marginTop: 0 }}>Здесь появятся сборки, которые вы сохраните кнопкой «Поделиться сборкой».</p>
          <Link className="btn btn-primary" to="/recommend">Подобрать сборку</Link>
        </section>
      )}
      {builds && builds.length > 0 && (
        <ul className="saved-list">
          {builds.map((b) => (
            <li key={b.slug} className="panel saved-item">
              <div>
                <Link className="saved-title" to={`/b/${b.slug}`}>{b.title}</Link>
                <div className="muted saved-meta">
                  {SCENARIO_TITLES[b.params.scenario]}
                  {b.params.scenario === 'gaming' && `, ${b.params.resolution}`} · бюджет {rub(b.params.budget)} ·
                  сохранена {dateFormat.format(new Date(b.created_at))}
                </div>
              </div>
              <span className="num saved-price">{rub(b.saved_price)}</span>
              <button type="button" className="btn btn-ghost btn-small" aria-label={`Удалить сборку «${b.title}»`}
                onClick={() => remove(b.slug)}>
                Удалить
              </button>
            </li>
          ))}
        </ul>
      )}

      <div className="account-actions">
        <button type="button" className="btn btn-ghost" onClick={() => signOut(false)}>Выйти</button>
        <button type="button" className="link-btn" onClick={() => signOut(true)}>Выйти на всех устройствах</button>
      </div>
    </div>
  )
}
