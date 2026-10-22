import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import App from '../App'
import { mockApi, requestsTo } from '../test/api'
import type { SavedBuildSummary, User } from '../types'

const ivan: User = { id: 1, email: 'ivan@example.com' }
const PASSWORD = 'correct horse'

function summary(slug: string, title: string): SavedBuildSummary {
  return {
    slug, title, created_at: '2026-10-20T12:00:00Z', saved_price: 126_000,
    params: { budget: 130_000, scenario: 'gaming', resolution: '1440p', platform: null, cpu_id: null, gpu_id: null },
  }
}

/** Бэкенд с состоянием: кто вошёл и какие сборки сохранены */
function fakeServer({ loggedIn = false, builds = [] as SavedBuildSummary[] } = {}) {
  let user: User | null = loggedIn ? ivan : null
  let saved = [...builds]
  const unauthorized = { status: 401, json: { detail: 'Нужно войти в аккаунт.' } }
  return mockApi((path, body, method) => {
    const credentials = body as { email: string; password: string } | undefined
    switch (path) {
      case '/api/auth/me':
        return user ? { json: user } : unauthorized
      case '/api/auth/login':
        if (credentials?.email !== ivan.email || credentials.password !== PASSWORD) {
          return { status: 401, json: { detail: 'Неверная почта или пароль.' } }
        }
        user = ivan
        return { json: user }
      case '/api/auth/register':
        if (credentials?.email === ivan.email) return { status: 409, json: { detail: 'Этот адрес уже зарегистрирован. Попробуйте войти.' } }
        if ((credentials?.password.length ?? 0) < 8) return { status: 422, json: { detail: [] } }
        user = { id: 2, email: credentials!.email }
        return { status: 201, json: user }
      case '/api/auth/logout':
      case '/api/auth/logout-all':
        user = null
        return { status: 204, json: null }
      case '/api/builds':
        return user ? { json: saved } : unauthorized
    }
    if (path.startsWith('/api/builds/') && method === 'DELETE') {
      saved = saved.filter((b) => `/api/builds/${b.slug}` !== path)
      return { status: 204, json: null }
    }
  })
}

function renderAt(path: string) {
  window.history.replaceState({}, '', path)
  return render(<App />)
}

const header = () => within(screen.getByRole('banner'))
const fill = async (email: string, password: string) => {
  await userEvent.type(screen.getByLabelText('Почта'), email)
  await userEvent.type(screen.getByLabelText('Пароль'), password)
}

describe('вход и регистрация', () => {
  it('гость попадает на вход по кнопке в шапке и после входа видит свои сборки', async () => {
    fakeServer({ builds: [summary('abc123', 'Оптимальная')] })
    renderAt('/')

    await userEvent.click(await header().findByRole('link', { name: 'Войти' }))
    expect(window.location.pathname).toBe('/login')

    await fill(ivan.email, PASSWORD)
    await userEvent.click(screen.getByRole('button', { name: 'Войти' }))

    expect(await screen.findByRole('link', { name: 'Оптимальная' })).toHaveAttribute('href', '/b/abc123')
    expect(window.location.pathname).toBe('/account')
    expect(header().getByRole('link', { name: 'Личный кабинет' })).toHaveTextContent('I')
  })

  it('показывает ошибку сервера при неверном пароле', async () => {
    fakeServer()
    renderAt('/login')
    await fill(ivan.email, 'wrong password')
    await userEvent.click(screen.getByRole('button', { name: 'Войти' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('Неверная почта или пароль.')
    expect(window.location.pathname).toBe('/login')
  })

  it('регистрирует нового пользователя', async () => {
    const fetchMock = fakeServer()
    renderAt('/login')
    await userEvent.click(screen.getByRole('radio', { name: 'Регистрация' }))
    await fill('petr@example.com', 'new password')
    await userEvent.click(screen.getByRole('button', { name: 'Зарегистрироваться' }))

    expect(await screen.findByText('petr@example.com')).toBeInTheDocument()
    expect(screen.getByText(/кнопкой «Поделиться сборкой»/)).toBeInTheDocument()
    expect(requestsTo(fetchMock, '/api/auth/register')).toEqual([{ email: 'petr@example.com', password: 'new password' }])
  })

  it('объясняет, что адрес уже занят', async () => {
    fakeServer()
    renderAt('/login')
    await userEvent.click(screen.getByRole('radio', { name: 'Регистрация' }))
    await fill(ivan.email, PASSWORD)
    await userEvent.click(screen.getByRole('button', { name: 'Зарегистрироваться' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('Этот адрес уже зарегистрирован')
  })
})

describe('личный кабинет', () => {
  it('просит войти, если пользователь — гость', async () => {
    fakeServer()
    renderAt('/account')
    expect(await screen.findByText('Войдите, чтобы видеть сохранённые сборки.')).toBeInTheDocument()
  })

  it('удаляет сборку из списка', async () => {
    const fetchMock = fakeServer({ loggedIn: true, builds: [summary('abc123', 'Оптимальная'), summary('def456', 'Дешевле')] })
    renderAt('/account')

    await userEvent.click(await screen.findByRole('button', { name: 'Удалить сборку «Дешевле»' }))

    expect(screen.queryByRole('link', { name: 'Дешевле' })).not.toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Оптимальная' })).toBeInTheDocument()
    expect(fetchMock.mock.calls.some(([path, init]) => path === '/api/builds/def456' && init?.method === 'DELETE')).toBe(true)
  })

  it('выход возвращает на главную и меняет шапку', async () => {
    fakeServer({ loggedIn: true })
    renderAt('/account')
    await userEvent.click(await screen.findByRole('button', { name: 'Выйти' }))

    expect(window.location.pathname).toBe('/')
    expect(header().getByRole('link', { name: 'Войти' })).toBeInTheDocument()
  })
})
