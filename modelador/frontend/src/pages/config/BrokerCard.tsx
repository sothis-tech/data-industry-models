import { useTranslation } from 'react-i18next'
import { StatusMessage } from '../../components/StatusMessage'
import { useBroker } from '../../hooks/useBroker'

type Props = { onSave?: () => void }

export function BrokerCard({ onSave }: Props) {
  const { t } = useTranslation()
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
      <h2>{t('config.broker.title')}</h2>

      <div className="form-grid">
        <label>
          {t('config.broker.connName')}
          <input
            value={brokerName}
            onChange={(e) => setBrokerName(e.target.value)}
            placeholder="Kong"
          />
        </label>
        <label>
          {t('config.broker.kongUrl')}
          <input
            value={brokerUrl}
            onChange={(e) => setBrokerUrl(e.target.value)}
            placeholder="http://kong:8000"
          />
        </label>
        <label>
          {t('config.broker.tenant')}
          <span className="label-hint">
            {' '}
            {t('config.broker.tenantHint')}
          </span>
          <input
            value={brokerTenant}
            onChange={(e) => setBrokerTenant(e.target.value)}
            placeholder="planta_norte"
          />
        </label>
      </div>

      <form className="broker-connect-form" onSubmit={handleConnectSubmit}>
        <h3>{t('config.broker.keycloakCreds')}</h3>
        <p className="helper">
          {t('config.broker.credsHelper')}
        </p>
        <div className="form-grid">
          <label>
            {t('config.broker.username')}
            <input
              value={authUsername}
              onChange={(e) => setAuthUsername(e.target.value)}
              placeholder="ummc"
              autoComplete="username"
            />
          </label>
          <label>
            {t('config.broker.password')}
            <input
              value={authPassword}
              onChange={(e) => setAuthPassword(e.target.value)}
              placeholder={t('config.broker.passwordPlaceholder')}
              type="password"
              autoComplete="current-password"
            />
          </label>
        </div>

        <div className="actions-row">
          <button type="submit" disabled={checking || authBusy}>
            {checking || authBusy ? t('config.broker.connecting') : t('config.broker.connect')}
          </button>
          <button type="button" onClick={onSaveBroker} title={t('config.broker.saveTitle')}>
            {t('common.save')}
          </button>
          <button
            type="button"
            onClick={onDeactivate}
            disabled={!currentUrl}
            title={t('config.broker.deactivateTitle')}
          >
            {t('config.broker.deactivate')}
          </button>
        </div>
      </form>

      {status ? <StatusMessage message={status} /> : null}

      <h3>{t('config.broker.savedConnections')}</h3>
      {!brokers.length ? (
        <p className="helper">{t('config.broker.noConnections')}</p>
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
                    {currentKey === key ? <span className="active-pill">{t('config.broker.active')}</span> : null}
                    {loggedIn ? (
                      <span className="active-pill">{t('config.broker.loggedIn')}</span>
                    ) : (
                      <span className="active-pill active-pill--muted">{t('config.broker.noSession')}</span>
                    )}
                  </div>
                  <p className="broker-url">{b.url}</p>
                  {b.tenant ? <p className="broker-tenant">{t('config.broker.tenantLabel', { tenant: b.tenant })}</p> : null}
                </div>
                <div className="broker-actions broker-actions--split">
                  <button type="button" onClick={() => onLoadConnection(b)} disabled={authBusy}>
                    {t('config.broker.use')}
                  </button>
                  <div className="broker-actions-right">
                    <button type="button" onClick={() => void onLogout(b)} disabled={authBusy || !loggedIn}>
                      {t('config.broker.logout')}
                    </button>
                    <button
                      type="button"
                      className="danger"
                      title={t('config.broker.deleteTitle', { name: b.name })}
                      onClick={() => onDelete(b)}
                    >
                      {t('common.delete')}
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
