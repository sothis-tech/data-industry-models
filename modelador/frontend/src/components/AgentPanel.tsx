import type { RefObject } from 'react'
import { useTranslation } from 'react-i18next'
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
  const { t } = useTranslation()
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
      aria-label={t('agent.panel.ariaLabel')}
    >
      {!isExpanded && isOpen && (
        <div
          className="agent-panel-resizer"
          role="separator"
          aria-orientation="vertical"
          aria-label={t('agent.panel.resizeAria')}
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
        aria-label={isOpen ? t('agent.panel.closeAria') : t('agent.panel.openAria')}
        title={isOpen ? t('agent.panel.closeTitle') : t('agent.panel.openTitle')}
      >
        <HeadsetIcon size={16} />
        <span>Marvin</span>
      </button>
    </aside>
  )
}
