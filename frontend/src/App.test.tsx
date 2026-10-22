import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { act } from 'react'
import { describe, expect, it } from 'vitest'
import App from './App'
import { mockApi } from './test/api'

function renderApp(path = '/') {
  window.history.replaceState({}, '', path)
  mockApi()
  return render(<App />)
}

const nav = () => within(screen.getByRole('navigation', { name: 'Главная навигация' }))
const heading = () => screen.getByRole('heading', { level: 1 })

describe('навигация', () => {
  it('показывает все разделы в главном меню', () => {
    renderApp()
    expect(nav().getAllByRole('link').map((a) => a.getAttribute('href'))).toEqual(['/', '/recommend', '/manual', '/info'])
  })

  it('переходит по ссылке без перезагрузки и подсвечивает пункт меню', async () => {
    renderApp()
    await userEvent.click(nav().getByRole('link', { name: 'База знаний' }))

    expect(window.location.pathname).toBe('/info')
    expect(heading()).toHaveTextContent('Знать своё железо')
    expect(nav().getByRole('link', { name: 'База знаний' })).toHaveClass('active')
    expect(nav().getByRole('link', { name: 'Главная' })).not.toHaveClass('active')
  })

  it('реагирует на кнопки «назад» и «вперёд» браузера', async () => {
    renderApp('/info')
    await act(async () => {
      window.history.pushState({}, '', '/recommend')
      window.dispatchEvent(new PopStateEvent('popstate'))
    })
    expect(heading()).toHaveTextContent('Подберём компьютер')
  })

  it('сохраняет введённый запрос при уходе со страницы подбора и возврате', async () => {
    renderApp('/recommend')
    await userEvent.type(screen.getByLabelText('Опишите словами'), 'игры до 90к')
    await userEvent.click(nav().getByRole('link', { name: 'Главная' }))
    await userEvent.click(nav().getByRole('link', { name: 'Подбор' }))

    expect(screen.getByLabelText('Опишите словами')).toHaveValue('игры до 90к')
  })

  it('показывает заглушку для неизвестного адреса', () => {
    renderApp('/nope')
    expect(heading()).toHaveTextContent('Здесь пока ничего нет.')
  })
})
