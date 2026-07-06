import { StatusMessage } from '../../components/StatusMessage'
import { useBroker } from '../../hooks/useBroker'

type Props = { onSave?: () => void }

export function BrokerCard({ onSave }: Props) {
  const {
    brokerName,
    setBrokerName,
    brokerUrl,
    setBrokerUrl,
    brokerTenant,
    setBrokerTenant,
    brokers,
    currentUrl,
    currentKey,
    status,
    checking,
    authUsername,
    setAuthUsername,
    authPassword,
    setAuthPassword,
    authBusy,
    authByKey,
    authKey,
    onCheckAndLogin,
    onLogout,
    onSave: onSaveBroker,
    onLoadConnection,
    onDeactivate,
    onDelete,
  } = useBroker(onSave)

  function handleConnectSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault()
    void onCheckAndLogin()
  }

  return (
    <div className="config-card">
      <h2>Conexión Orion (tenant)</h2>

      <div className="form-grid">
        <label>
          Nombre de la conexión
          <input
            value={brokerName}
            onChange={(e) => setBrokerName(e.target.value)}
            placeholder="Kong"
          />
        </label>
        <label>
          URL base Kong
          <input
            value={brokerUrl}
            onChange={(e) => setBrokerUrl(e.target.value)}
            placeholder="http://kong:8000"
          />
        </label>
        <label>
          Tenant / NGSILD-Tenant
          <span className="label-hint">
            {' '}
            — espacio NGSI-LD autorizado por el rol tenant_* en Keycloak
          </span>
          <input
            value={brokerTenant}
            onChange={(e) => setBrokerTenant(e.target.value)}
            placeholder="planta_norte"
          />
        </label>
      </div>

      <form className="broker-connect-form" onSubmit={handleConnectSubmit}>
        <h3>Credenciales Keycloak</h3>
        <p className="helper">
          Usuario y contraseña solo se usan para conectar; no se guardan en el navegador.
        </p>
        <div className="form-grid">
          <label>
            Usuario
            <input
              value={authUsername}
              onChange={(e) => setAuthUsername(e.target.value)}
              placeholder="ummc"
              autoComplete="username"
            />
          </label>
          <label>
            Contraseña
            <input
              value={authPassword}
              onChange={(e) => setAuthPassword(e.target.value)}
              placeholder="Contraseña Keycloak"
              type="password"
              autoComplete="current-password"
            />
          </label>
        </div>

        <div className="actions-row">
          <button type="submit" disabled={checking || authBusy}>
            {checking || authBusy ? 'Conectando…' : 'Conectar'}
          </button>
          <button type="button" onClick={onSaveBroker} title="Guardar URL, nombre y tenant sin credenciales">
            Guardar
          </button>
          <button
            type="button"
            onClick={onDeactivate}
            disabled={!currentUrl}
            title="Quitar la conexión activa sin borrar las guardadas"
          >
            Desactivar
          </button>
        </div>
      </form>

      {status ? <StatusMessage message={status} /> : null}

      <h3>Conexiones guardadas</h3>
      {!brokers.length ? (
        <p className="helper">No hay conexiones Orion guardadas.</p>
      ) : (
        <ul className="broker-list">
          {brokers.map((b) => {
            const key = authKey(b.url, b.tenant)
            const loggedIn = authByKey[key]
            return (
              <li key={key} className="broker-list-item">
                <div className="broker-info">
                  <div className="broker-title-row">
                    <strong>{b.name}</strong>
                    {currentKey === key ? <span className="active-pill">activa</span> : null}
                    {loggedIn ? (
                      <span className="active-pill">sesión iniciada</span>
                    ) : (
                      <span className="active-pill active-pill--muted">sin sesión</span>
                    )}
                  </div>
                  <p className="broker-url">{b.url}</p>
                  {b.tenant ? <p className="broker-tenant">tenant: {b.tenant}</p> : null}
                </div>
                <div className="broker-actions broker-actions--split">
                  <button type="button" onClick={() => onLoadConnection(b)} disabled={authBusy}>
                    Usar
                  </button>
                  <div className="broker-actions-right">
                    <button type="button" onClick={() => void onLogout(b)} disabled={authBusy || !loggedIn}>
                      Cerrar sesión
                    </button>
                    <button
                      type="button"
                      className="danger"
                      title={`Eliminar conexión "${b.name}"`}
                      onClick={() => onDelete(b)}
                    >
                      Eliminar
                    </button>
                  </div>
                </div>
              </li>
            )
          })}
        </ul>
      )}
    </div>
  )
}
