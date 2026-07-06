import type { RefObject } from 'react'
import { useAgentPanelResize } from '../hooks/useAgentPanelResize'
import type { StoredBroker } from '../types/broker'
import { AgentPanelShell } from './AgentPanelShell'
import { HeadsetIcon } from './AgentIcons'

type Props = {
  bodyRef: RefObject<HTMLDivElement | null>
  broker: StoredBroker | null
  isOrionAuthenticated: boolean
}

export function AgentPanel({ bodyRef, broker, isOrionAuthenticated }: Props) {
  const {
    isOpen,
    isExpanded,
    togglePanel,
    closePanel,
    toggleExpanded,
    panelWidth,
    asideWidth,
    resizerProps,
  } = useAgentPanelResize(bodyRef)

  return (
    <aside
      className={`agent-panel${isOpen ? ' agent-panel--open' : ''}${isExpanded ? ' agent-panel--expanded' : ''}`}
      style={{ width: asideWidth }}
      aria-label="Marvin — Asistente"
    >
      {!isExpanded && isOpen && (
        <div
          className="agent-panel-resizer"
          role="separator"
          aria-orientation="vertical"
          aria-label="Redimensionar panel del asistente"
          tabIndex={0}
          {...resizerProps}
        />
      )}
      <div
        className={`agent-panel-inner${isOpen ? '' : ' agent-panel-inner--collapsed'}`}
        style={{ width: isOpen ? panelWidth : 0 }}
        aria-hidden={!isOpen}
      >
        <AgentPanelShell
          broker={broker}
          isOrionAuthenticated={isOrionAuthenticated}
          isPanelOpen={isOpen}
          isExpanded={isExpanded}
          onClose={closePanel}
          onToggleExpand={toggleExpanded}
        />
      </div>

      <button
        type="button"
        className="agent-panel-rail"
        onClick={togglePanel}
        aria-expanded={isOpen}
        aria-label={isOpen ? 'Cerrar panel de Marvin' : 'Abrir panel de Marvin'}
        title={isOpen ? 'Cerrar Marvin' : 'Abrir Marvin'}
      >
        <HeadsetIcon size={16} />
        <span>Marvin</span>
      </button>
    </aside>
  )
}
