import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'
import { type BrokerHealthState, type ModelSummary } from '../hooks/useAppStatus'
import type { ContextReachability } from '../lib/contextReachability'
import type { StoredBroker } from '../types/broker'

const dotClass: Record<BrokerHealthState, string> = {
  unknown: 'sb-dot sb-dot--yellow',
  ok: 'sb-dot sb-dot--green',
  'no-session': 'sb-dot sb-dot--yellow',
  error: 'sb-dot sb-dot--red',
}

const contextDotClass: Record<ContextReachability, string> = {
  unknown: 'sb-dot sb-dot--yellow',
  ok: 'sb-dot sb-dot--green',
  unreachable: 'sb-dot sb-dot--red',
  none: 'sb-dot',
}

type Props = {
  broker: StoredBroker | null
  health: BrokerHealthState
  model: ModelSummary
  contextReachability?: ContextReachability
}

function connectionLabel(broker: StoredBroker): string {
  return broker.name.trim().toLowerCase().startsWith('kong') ? 'Kong' : broker.name
}

export function StatusBar({
  broker,
  health,
  model,
  contextReachability = 'none',
}: Props) {
  const { t } = useTranslation()

  function healthLabel(health: BrokerHealthState): string {
    if (health === 'ok') return t('status.loggedIn')
    if (health === 'no-session') return t('status.noSession')
    if (health === 'error') return t('status.unavailable')
    return t('status.checking')
  }

  function contextLabel(state: ContextReachability): string {
    if (state === 'ok') return t('status.contextOk')
    if (state === 'unreachable') return t('status.contextUnreachable')
    if (state === 'unknown') return t('status.contextChecking')
    return t('status.contextNoUrl')
  }

  return (
    <div className="status-bar">
      {broker ? (
        <span className="sb-indicator">
          <span className={dotClass[health]} />
          <span>
            {connectionLabel(broker)}: {healthLabel(health)}
          </span>
        </span>
      ) : (
        <span className="sb-indicator">
          <span className="sb-dot" />
          <span>
            {t('status.noConnection')} —{' '}
            <Link to="/" className="sb-link">
              {t('status.configure')}
            </Link>
          </span>
        </span>
      )}

      {model.loaded ? (
        <span className="sb-indicator">
          <span className="sb-dot sb-dot--green" />
          <span>{t('status.model', { label: model.label })}</span>
        </span>
      ) : (
        <span className="sb-indicator">
          <span className="sb-dot" />
          <span>
            {t('status.modelNotLoaded')} —{' '}
            <Link to="/" className="sb-link">
              {t('status.configure')}
            </Link>
          </span>
        </span>
      )}

      {model.loaded && contextReachability !== 'none' ? (
        <span className="sb-indicator" title={contextLabel(contextReachability)}>
          <span className={contextDotClass[contextReachability]} />
          <span>{contextLabel(contextReachability)}</span>
        </span>
      ) : null}
    </div>
  )
}
