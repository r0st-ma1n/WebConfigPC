/* oxlint-disable react/only-export-components */
import { createContext, useContext, useEffect, useState, type ReactNode } from 'react'

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

export function Link({ to, children, ...props }: { to: string; children: ReactNode; className?: string }) {
  const { navigate } = useContext(PathContext)
  return <a href={to} {...props} onClick={(event) => {
    event.preventDefault()
    if (window.location.pathname !== to) window.history.pushState({}, '', to)
    navigate(to)
    window.scrollTo({ top: 0, behavior: 'instant' })
  }}>{children}</a>
}

export function NavLink({ to, children, className, ...props }: { to: string; children: ReactNode; className?: string; end?: boolean }) {
  return <Link to={to} className={className} {...props}>{children}</Link>
}

export function RouteView({ path, routes, fallback }: { path: string; routes: Record<string, ReactNode>; fallback: ReactNode }) {
  return <>{routes[path] ?? fallback}</>
}
