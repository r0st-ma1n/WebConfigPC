// Вход и регистрация на одной странице: переключатель режима над формой
import { useState } from 'react'
import { ApiError } from '../api'
import { useAuth } from '../auth'
import { Segmented } from '../components/Segmented'
import { Link, useNavigate } from '../router'

type Mode = 'login' | 'register'

export function LoginPage() {
  const auth = useAuth()
  const navigate = useNavigate()
  const [mode, setMode] = useState<Mode>('login')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  if (auth.user) {
    return (
      <div className="content-page auth-page">
        <h1>Вы уже вошли</h1>
        <p className="lead">Аккаунт: {auth.user.email}</p>
        <Link className="btn btn-primary" to="/account">Мои сборки</Link>
      </div>
    )
  }

  async function submit() {
    setBusy(true)
    setError(null)
    try {
      await (mode === 'login' ? auth.login(email, password) : auth.register(email, password))
      navigate('/account')
    } catch (e) {
      // 422 — сервер не принял почту или пароль; подробности валидации пользователю не нужны
      setError(e instanceof ApiError && e.status !== 422 ? e.message : 'Проверьте адрес почты и пароль (не короче 8 символов).')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="content-page auth-page">
      <div className="eyebrow"><span className="eyebrow-line" />ЛИЧНЫЙ КАБИНЕТ</div>
      <h1>{mode === 'login' ? 'Вход' : 'Регистрация'}</h1>
      <p className="lead">Сохраняйте сборки в аккаунт, чтобы вернуться к ним с любого устройства.</p>
      <form className="panel auth-form" onSubmit={(e) => { e.preventDefault(); submit() }}>
        <Segmented<Mode>
          label="Режим"
          value={mode}
          options={[{ value: 'login', title: 'Вход' }, { value: 'register', title: 'Регистрация' }]}
          onChange={(m) => { setMode(m); setError(null) }}
        />
        <div className="field">
          <label htmlFor="email">Почта</label>
          <input id="email" className="input" type="email" autoComplete="email" required
            value={email} onChange={(e) => setEmail(e.target.value)} />
        </div>
        <div className="field">
          <label htmlFor="password">Пароль</label>
          <input id="password" className="input" type="password" required minLength={8} maxLength={128}
            autoComplete={mode === 'login' ? 'current-password' : 'new-password'}
            value={password} onChange={(e) => setPassword(e.target.value)} />
          {mode === 'register' && <span className="muted field-hint">Не короче 8 символов</span>}
        </div>
        {error && <p className="notice notice-error" role="alert" style={{ margin: 0 }}>{error}</p>}
        <button className="btn btn-primary" disabled={busy}>
          {mode === 'login' ? (busy ? 'Вхожу…' : 'Войти') : (busy ? 'Создаю аккаунт…' : 'Зарегистрироваться')}
        </button>
      </form>
    </div>
  )
}
