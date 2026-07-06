import { useState } from 'react'
import { useOutletContext } from 'react-router-dom'
import { BrokerCard } from './BrokerCard'
import { ModelCard } from './ModelCard'
import { OnboardingCard } from './OnboardingCard'
import { RagCard } from './RagCard'
import type { BrokerHealthState } from '../../hooks/useAppStatus'
import type { StoredBroker } from '../../types/broker'

type OutletCtx = {
  broker: StoredBroker | null
  health: BrokerHealthState
  refreshKey: number
  triggerRefresh: () => void
}

function DocIcon() {
  return (
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor"
      strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
      <polyline points="14 2 14 8 20 8"/>
      <line x1="16" y1="13" x2="8" y2="13"/>
      <line x1="16" y1="17" x2="8" y2="17"/>
      <polyline points="10 9 9 9 8 9"/>
    </svg>
  )
}

export function ConfigPage() {
  const { broker, health, refreshKey, triggerRefresh } = useOutletContext<OutletCtx>()
  const [sidebarOpen, setSidebarOpen] = useState(false)

  return (
    <div className="config-layout">
      {/* ── Sidebar RAG (izquierda) ── */}
      <aside className={`rag-sidebar${sidebarOpen ? ' rag-sidebar--open' : ''}`}>
        {/* Lengüeta vertical siempre visible */}
        <button
          className="rag-sidebar-rail"
          onClick={() => setSidebarOpen((o) => !o)}
          aria-expanded={sidebarOpen}
          aria-label={sidebarOpen ? 'Cerrar panel RAG' : 'Abrir panel RAG'}
        >
          <DocIcon />
          <span>RAG</span>
        </button>

        {/* Panel expandido */}
        <div className="rag-sidebar-panel" aria-hidden={!sidebarOpen}>
          <div className="rag-sidebar-header">
            <DocIcon />
            <strong>Documentación RAG</strong>
            <button
              className="rag-sidebar-close"
              onClick={() => setSidebarOpen(false)}
              aria-label="Cerrar panel RAG"
            >
              ✕
            </button>
          </div>
          <div className="rag-sidebar-body">
            <RagCard
              activeBrokerUrl={broker?.url}
              activeTenant={broker?.tenant}
              isOrionAuthenticated={health === 'ok'}
              ragPanelOpen={sidebarOpen}
            />
          </div>
        </div>
      </aside>

      {/* ── Contenido principal ── */}
      <div className="config-main">
        <div className="page-inner">
          <OnboardingCard refreshKey={refreshKey} />
          <div className="config-grid">
            <BrokerCard onSave={triggerRefresh} />
            <ModelCard onSave={triggerRefresh} />
          </div>
        </div>
      </div>
    </div>
  )
}
