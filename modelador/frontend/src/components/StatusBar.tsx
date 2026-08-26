import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'
import { type BrokerHealthState, type ModelSummary } from '../hooks/useAppStatus'
import type { StoredBroker } from '../types/broker'
const dotClass: Record<BrokerHealthState, string> = {
  unknown: 'sb-dot sb-dot--yellow',
  ok: 'sb-dot sb-dot--green',
  'no-session': 'sb-dot sb-dot--yellow',
  error: 'sb-dot sb-dot--red',
}
type Props = {
  broker: StoredBroker | null
  health: BrokerHealthState
  model: ModelSummary
}
function connectionLabel(broker: StoredBroker): string {
  return broker.name.trim().toLowerCase().startsWith('kong') ? 'Kong' : broker.name
}
export function StatusBar({ broker, health, model }: Props) {
  const { t } = useTranslation()
  function healthLabel(h: BrokerHealthState): string {
    if (h === 'ok') return t('status.loggedIn')
    if (h === 'no-session') return t('status.noSession')
    if (h === 'error') return t('status.unavailable')
    return t('status.checking')
  }
  return (
    <div className="status-bar">
      {broker ? (
        <span className="sb-indicator">
          <span className={dotClass[health]} />
          <span>{connectionLabel(broker)}: {healthLabel(health)}</span>
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
    </div>
  )
}
