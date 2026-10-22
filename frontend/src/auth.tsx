/* oxlint-disable react/only-export-components */
// Текущий пользователь: загружается при открытии сайта и обновляется после входа и выхода
import { createContext, useContext, useEffect, useState, type ReactNode } from 'react'
import { api } from './api'
import type { User } from './types'

interface AuthState {
  /** undefined — ещё не знаем (идёт запрос), null — гость */
  user: User | null | undefined
  login: (email: string, password: string) => Promise<void>
  register: (email: string, password: string) => Promise<void>
  logout: (everywhere?: boolean) => Promise<void>
}

const notReady = () => Promise.reject(new Error('AuthProvider не подключён'))
// Без провайдера (например, в тестах отдельных компонентов) пользователь — гость
const AuthContext = createContext<AuthState>({ user: null, login: notReady, register: notReady, logout: notReady })

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null | undefined>(undefined)

  useEffect(() => {
    // 401 — обычный гость; при недоступном сервере тоже считаем гостем
    api.me().then(setUser).catch(() => setUser(null))
  }, [])

  const state: AuthState = {
    user,
    login: async (email, password) => setUser(await api.login(email, password)),
    register: async (email, password) => setUser(await api.register(email, password)),
    logout: async (everywhere = false) => {
      await (everywhere ? api.logoutAll() : api.logout())
      setUser(null)
    },
  }
  return <AuthContext.Provider value={state}>{children}</AuthContext.Provider>
}

export function useAuth(): AuthState {
  return useContext(AuthContext)
}
