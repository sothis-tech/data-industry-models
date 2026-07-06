import type { StoredBroker } from '../types/broker'
import { AgentChat } from './AgentChat'
import { HeadsetIcon } from './AgentIcons'

type Props = {
  broker: StoredBroker | null
  isOrionAuthenticated: boolean
  isPanelOpen: boolean
  isExpanded: boolean
  onClose: () => void
  onToggleExpand: () => void
}

function ExpandIcon({ expanded }: { expanded: boolean }) {
  if (expanded) {
    return (
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
        <polyline points="4 14 10 14 10 20" />
        <polyline points="20 10 14 10 14 4" />
        <line x1="14" y1="10" x2="21" y2="3" />
        <line x1="3" y1="21" x2="10" y2="14" />
      </svg>
    )
  }
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
      <polyline points="15 3 21 3 21 9" />
      <polyline points="9 21 3 21 3 15" />
      <line x1="21" y1="3" x2="14" y2="10" />
      <line x1="3" y1="21" x2="10" y2="14" />
    </svg>
  )
}

export function AgentPanelShell({
  broker,
  isOrionAuthenticated,
  isPanelOpen,
  isExpanded,
  onClose,
  onToggleExpand,
}: Props) {
  return (
    <div className="agent-panel-shell">
      <header className="agent-panel-header">
        <div className="agent-panel-header-avatar">
          <HeadsetIcon size={18} />
        </div>
        <div className="agent-panel-header-info">
          <strong>Marvin</strong>
        </div>
        <div className="agent-panel-header-actions">
          <button
            type="button"
            className="agent-panel-icon-btn"
            onClick={onToggleExpand}
            aria-pressed={isExpanded}
            aria-label={isExpanded ? 'Restaurar ancho del panel' : 'Ampliar panel'}
            title={isExpanded ? 'Restaurar ancho' : 'Ampliar panel'}
          >
            <ExpandIcon expanded={isExpanded} />
          </button>
          <button type="button" className="agent-panel-close" onClick={onClose} aria-label="Cerrar panel de Marvin">
            ✕
          </button>
        </div>
      </header>

      <AgentChat
        broker={broker}
        isOrionAuthenticated={isOrionAuthenticated}
        isPanelOpen={isPanelOpen}
      />
    </div>
  )
}
