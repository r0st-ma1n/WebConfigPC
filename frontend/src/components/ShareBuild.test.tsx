import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import { AuthProvider, useAuth } from '../auth'
import { mockApi } from '../test/api'
import { cpu, gpu, recommendation } from '../test/fixtures'
import type { RecommendParams } from '../types'
import { ShareBuild } from './ShareBuild'

const rec = recommendation('optimal', 'Оптимальная', [cpu, gpu], 75)
const params: RecommendParams = { budget: 100_000, scenario: 'gaming', resolution: '1440p', platform: null, cpu_id: null, gpu_id: null }
const user = { id: 1, email: 'ivan@example.com' }

/** Вход «из другой части страницы»; почта появляется, когда пользователь загружен */
function LoginButton() {
  const auth = useAuth()
  return <>
    <button type="button" onClick={() => auth.login(user.email, 'password')}>Тестовый вход</button>
    {auth.user && <span>{auth.user.email}</span>}
  </>
}

function renderShare({ loggedIn }: { loggedIn: boolean }) {
  let slugs = 0
  let current = loggedIn ? user : null
  const fetchMock = mockApi((path) => {
    if (path === '/api/auth/me') return current ? { json: current } : undefined
    if (path === '/api/auth/login') { current = user; return { json: user } }
    if (path === '/api/builds') return { status: 201, json: { slug: `slug${++slugs}` } }
  })
  render(<AuthProvider><ShareBuild rec={rec} params={params} /><LoginButton /></AuthProvider>)
  return fetchMock
}

const share = () => userEvent.click(screen.getByRole('button', { name: 'Поделиться сборкой' }))

describe('кнопка «Поделиться»', () => {
  it('гостю показывает ссылку и предлагает войти', async () => {
    renderShare({ loggedIn: false })
    await share()

    expect(screen.getByLabelText('Ссылка на сборку')).toHaveValue(`${window.location.origin}/b/slug1`)
    expect(screen.getByRole('link', { name: 'Войдите' })).toHaveAttribute('href', '/login')
  })

  it('вошедшему сообщает, что сборка в «Мои сборки»', async () => {
    renderShare({ loggedIn: true })
    await screen.findByText(user.email)
    await share()

    expect(screen.getByRole('link', { name: '«Мои сборки»' })).toHaveAttribute('href', '/account')
  })

  it('после входа предлагает сохранить ещё раз, а не врёт, что сборка уже в аккаунте', async () => {
    const fetchMock = renderShare({ loggedIn: false })
    await share()
    await userEvent.click(screen.getByRole('button', { name: 'Тестовый вход' }))

    expect(screen.queryByRole('link', { name: '«Мои сборки»' })).not.toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Сохранить в «Мои сборки»' }))

    expect(screen.getByLabelText('Ссылка на сборку')).toHaveValue(`${window.location.origin}/b/slug2`)
    expect(screen.getByRole('link', { name: '«Мои сборки»' })).toBeInTheDocument()
    expect(fetchMock.mock.calls.filter(([path]) => path === '/api/builds')).toHaveLength(2)
  })
})
