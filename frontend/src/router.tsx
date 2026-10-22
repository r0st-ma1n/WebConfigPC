/* oxlint-disable react/only-export-components */
import { createContext, useContext, useEffect, useState, type AnchorHTMLAttributes, type ReactNode } from 'react'

const PathContext = createContext<{ path: string; navigate: (path: string) => void }>({ path: '/', navigate: () => {} })

export function Router({ children }: { children: ReactNode }) {
  const [path, setPath] = useState(window.location.pathname)
  useEffect(() => {
    const update = () => setPath(window.location.pathname)
    window.addEventListener('popstate', update)
    return () => window.removeEventListener('popstate', update)
  }, [])
  return <PathContext.Provider value={{ path, navigate: setPath }}>{children}</PathContext.Provider>
}

export function usePath() { return useContext(PathContext).path }

/** Переход из кода (после входа, выхода): то же, что нажатие на ссылку */
export function useNavigate() {
  const { navigate } = useContext(PathContext)
  return (to: string) => {
    if (window.location.pathname !== to) window.history.pushState({}, '', to)
    navigate(to)
    window.scrollTo({ top: 0, behavior: 'instant' })
  }
}

export function Link({ to, children, ...props }: { to: string; children: ReactNode } & AnchorHTMLAttributes<HTMLAnchorElement>) {
  const navigate = useNavigate()
  return <a href={to} {...props} onClick={(event) => {
    props.onClick?.(event)
    if (event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return
    event.preventDefault()
    navigate(to)
  }}>{children}</a>
}

export function NavLink({ to, children, className }: { to: string; children: ReactNode; className?: string; end?: boolean }) {
  // end нужен только вызывающему коду для подсветки активного пункта — в <a> его не передаём,
  // иначе React предупреждает о неизвестном атрибуте
  return <Link to={to} className={className}>{children}</Link>
}

export function RouteView({ path, routes, fallback }: { path: string; routes: Record<string, ReactNode>; fallback: ReactNode }) {
  return <>{routes[path] ?? fallback}</>
}
