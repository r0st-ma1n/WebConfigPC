import { useEffect, useState } from 'react'
import { api } from './api'
import { ManualPage } from './pages/ManualPage'
import { RecommendPage } from './pages/RecommendPage'
import type { AiStatus } from './types'

type Tab = 'recommend' | 'manual'

export default function App() {
  const [tab, setTab] = useState<Tab>('recommend')
  const [ai, setAi] = useState<AiStatus | null>(null)

  useEffect(() => {
    api.aiStatus().then(setAi).catch(() => setAi(null))
  }, [])

  return (
    <>
      <header className="topbar">
        <span className="brand">Сборщик ПК</span>
        <nav className="tabs" role="tablist" aria-label="Режим">
          <button type="button" role="tab" className="tab" aria-selected={tab === 'recommend'} onClick={() => setTab('recommend')}>
            Подбор
          </button>
          <button type="button" role="tab" className="tab" aria-selected={tab === 'manual'} onClick={() => setTab('manual')}>
            Ручная сборка
          </button>
        </nav>
        {ai && (
          <span className="ai-badge">
            {ai.enabled ? <>ИИ: <strong>{ai.model}</strong></> : 'Работает без ИИ'}
          </span>
        )}
      </header>
      {/* Обе страницы остаются смонтированными, чтобы при переключении не терялось состояние */}
      <div className="page" hidden={tab !== 'recommend'}><RecommendPage ai={ai} /></div>
      <div className="page" hidden={tab !== 'manual'}><ManualPage /></div>
    </>
  )
}
