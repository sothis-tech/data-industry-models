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

function healthLabel(health: BrokerHealthState): string {
  if (health === 'ok') return 'sesión iniciada'
  if (health === 'no-session') return 'sin sesión'
  if (health === 'error') return 'estado no disponible'
  return 'comprobando sesión'
}

export function StatusBar({ broker, health, model }: Props) {
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
            Sin conexión Orion —{' '}
            <Link to="/" className="sb-link">
              Configurar
            </Link>
          </span>
        </span>
      )}

      {model.loaded ? (
        <span className="sb-indicator">
          <span className="sb-dot sb-dot--green" />
          <span>Modelo: {model.label}</span>
        </span>
      ) : (
        <span className="sb-indicator">
          <span className="sb-dot" />
          <span>
            Modelo no cargado —{' '}
            <Link to="/" className="sb-link">
              Configurar
            </Link>
          </span>
        </span>
      )}
    </div>
  )
}
