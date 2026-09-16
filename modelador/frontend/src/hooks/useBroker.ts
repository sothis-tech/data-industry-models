import { useCallback, useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { formatAgentConnectStatus, postAgentConnect } from '../api/agentConnect'
import { createContextTenant, deleteContextTenant } from '../api/contextServer'
import { createRagTenant } from '../api/rag'
import { refreshModelFromServer } from '../lib/modelStore'
import {
  checkOrionAuth,
  getOrionAuthStatus,
  loginOrion,
  logoutOrion,
} from '../api/orion'
import { ORION_SESSION_LOST } from '../lib/orionSessionEvents'
import {
  clearCurrentBroker,
  getCurrentBroker,
  getStoredBrokers,
  setCurrentBroker,
  setStoredBrokers,
} from '../lib/storage'
import type { StoredBroker } from '../types/broker'

function authKey(url: string, tenant?: string) {
  return `${url.trim()}::${tenant?.trim() ?? ''}`
}

/**
 * Alta (idempotente) del espacio del tenant en el servidor de contexto y
 * sincronización del modelo. Los fallos no bloquean la conexión al broker.
 */
function ensureContextSpace(tenant: string) {
  void createContextTenant(tenant)
    .catch(() => {})
    .then(() => refreshModelFromServer())
}

export function useBroker(onSave?: () => void) {
  const { t } = useTranslation()
  const init = getCurrentBroker()
  const [brokerName, setBrokerName] = useState(init?.name ?? '')
  const [brokerUrl, setBrokerUrl] = useState(init?.url ?? '')
  const [brokerTenant, setBrokerTenant] = useState(init?.tenant ?? '')
  const [brokers, setBrokers] = useState<StoredBroker[]>(() => getStoredBrokers())
  const [currentUrl, setCurrentUrl] = useState<string | null>(init?.url ?? null)
  const [currentKey, setCurrentKey] = useState<string | null>(init ? authKey(init.url, init.tenant) : null)
  const [status, setStatus] = useState<string | null>(null)
  const [checking, setChecking] = useState(false)
  const [authUsername, setAuthUsername] = useState('')
  const [authPassword, setAuthPassword] = useState('')
  const [authBusy, setAuthBusy] = useState(false)
  const [authByKey, setAuthByKey] = useState<Record<string, boolean>>({})

  const refreshAuthStatuses = useCallback(async () => {
    const entries = await Promise.all(
      getStoredBrokers().map(async (b) => {
        const { loggedIn } = await getOrionAuthStatus(b.url, b.tenant)
        return [authKey(b.url, b.tenant), loggedIn] as const
      }),
    )
    setAuthByKey(Object.fromEntries(entries))
  }, [])

  useEffect(() => {
    void refreshAuthStatuses()
  }, [refreshAuthStatuses])

  useEffect(() => {
    function onSessionLost() {
      setAuthByKey((prev) => {
        const next = { ...prev }
        for (const key of Object.keys(next)) next[key] = false
        return next
      })
    }
    window.addEventListener(ORION_SESSION_LOST, onSessionLost)
    return () => window.removeEventListener(ORION_SESSION_LOST, onSessionLost)
  }, [])

  async function onCheckAndLogin(target?: StoredBroker) {
    const url = (target?.url ?? brokerUrl).trim()
    const tenant = (target?.tenant ?? brokerTenant).trim() || undefined
    const name = (target?.name ?? brokerName).trim() || url
    if (!url) {
      setStatus(t('config.broker.status.needUrl'))
      return
    }
    if (!tenant) {
      setStatus(t('config.broker.status.needTenant'))
      return
    }
    setBrokerName(name)
    setBrokerUrl(url)
    setBrokerTenant(tenant)
    setChecking(true)
    setAuthBusy(true)
    setStatus(t('config.broker.status.checking'))
    const username = authUsername.trim()
    if (!username || !authPassword) {
      setStatus(t('config.broker.status.needCredentials'))
      setChecking(false)
      setAuthBusy(false)
      return
    }
    const { ok, data } = await checkOrionAuth(url, tenant, { username, password: authPassword })
    if (ok) {
      const login = await loginOrion(url, tenant, username, authPassword)
      if (login.ok) {
        setCurrentBroker(name, url, tenant)
        setCurrentUrl(url)
        setCurrentKey(authKey(url, tenant))
        setAuthPassword('')
        setAuthByKey((s) => ({ ...s, [authKey(url, tenant)]: true }))
        onSave?.()
        ensureContextSpace(tenant)

        const agentConnect = await postAgentConnect(tenant, url)
        if (agentConnect.error || agentConnect.status >= 400) {
          void createRagTenant(tenant).catch(() => {})
          setStatus(
            t('config.broker.status.connectedAgentWarning', {
              name,
              error: agentConnect.error ?? `HTTP ${agentConnect.status}`,
            }),
          )
        } else {
          const summary = formatAgentConnectStatus(agentConnect.body)
          setStatus(t('config.broker.status.connected', { name, summary }))
        }
      } else {
        setStatus(
          t('config.broker.status.loginFailed', {
            error: login.error ?? t('config.broker.status.invalidCredentials'),
          }),
        )
      }
    } else {
      const err =
        (typeof data.detail === 'string' && data.detail) ||
        ('error' in data && typeof data.error === 'string' && data.error) ||
        t('config.broker.status.connectFailedHint')
      setStatus(t('config.broker.status.connectError', { error: err }))
    }
    setChecking(false)
    setAuthBusy(false)
  }

  function onSaveBroker() {
    const url = brokerUrl.trim()
    const name = brokerName.trim() || url
    const tenant = brokerTenant.trim() || undefined
    if (!url) {
      setStatus(t('config.broker.status.needUrl'))
      return
    }
    const next = [...brokers]
    const existing = next.findIndex((b) => authKey(b.url, b.tenant) === authKey(url, tenant))
    if (existing >= 0) {
      next[existing] = { name, url, tenant }
    } else {
      next.push({ name, url, tenant })
    }
    setStoredBrokers(next)
    setBrokers(next)
    setCurrentBroker(name, url, tenant)
    setCurrentUrl(url)
    setCurrentKey(authKey(url, tenant))
    setBrokerName(name)
    setStatus(t('config.broker.status.saved'))
    onSave?.()
    if (tenant) {
      ensureContextSpace(tenant)
      void createRagTenant(tenant).catch(() => {
        setStatus(t('config.broker.status.savedRagWarning'))
      })
    }
  }

  function onLoadConnection(b: StoredBroker) {
    setBrokerName(b.name)
    setBrokerUrl(b.url)
    setBrokerTenant(b.tenant ?? '')
    setAuthPassword('')
    setStatus(t('config.broker.status.activeConnection', { name: b.name }))
    const tn = b.tenant?.trim()
    if (tn) {
      ensureContextSpace(tn)
      void createRagTenant(tn).catch(() => {
        setStatus(t('config.broker.status.loadedRagWarning', { tenant: tn }))
      })
    }
  }

  async function onLogout(target?: StoredBroker) {
    const url = (target?.url ?? brokerUrl).trim()
    const tenant = (target?.tenant ?? brokerTenant).trim() || undefined
    if (!url) return
    setAuthBusy(true)
    const res = await logoutOrion(url, tenant)
    if (res.ok) {
      setAuthByKey((s) => ({ ...s, [authKey(url, tenant)]: false }))
      onSave?.()
      setStatus(t('config.broker.status.loggedOut'))
    } else {
      setStatus(
        t('config.broker.status.logoutFailed', {
          error: res.error ?? t('config.broker.status.unknownError'),
        }),
      )
    }
    setAuthBusy(false)
  }

  function onDeactivate() {
    if (!currentUrl) return
    clearCurrentBroker()
    setCurrentUrl(null)
    setCurrentKey(null)
    setBrokerName('')
    setBrokerUrl('')
    setBrokerTenant('')
    setAuthPassword('')
    onSave?.()
    setStatus(t('config.broker.status.deactivated'))
    void refreshModelFromServer()
  }

  function onDelete(b: StoredBroker) {
    const next = brokers.filter((x) => authKey(x.url, x.tenant) !== authKey(b.url, b.tenant))
    setStoredBrokers(next)
    setBrokers(next)

    const tn = b.tenant?.trim()
    if (tn) {
      const othersStillUseTenant = next.some((x) => x.tenant?.trim() === tn)
      if (othersStillUseTenant) {
        setStatus(t('config.broker.status.deletedTenantShared', { name: b.name, tenant: tn }))
      } else {
        const ok = window.confirm(t('config.broker.status.confirmDeleteTenantSpace', { tenant: tn }))
        if (ok) {
          void deleteContextTenant(tn).catch(() => {
            setStatus(t('config.broker.status.deletedTenantError', { tenant: tn }))
          })
          setStatus(t('config.broker.status.deletedWithTenant', { name: b.name, tenant: tn }))
        } else {
          setStatus(t('config.broker.status.deletedTenantKept', { name: b.name, tenant: tn }))
        }
      }
    } else {
      setStatus(t('config.broker.status.deleted', { name: b.name }))
    }

    if (currentKey === authKey(b.url, b.tenant)) {
      clearCurrentBroker()
      setCurrentUrl(null)
      setCurrentKey(null)
      setBrokerName('')
      setBrokerUrl('')
      setBrokerTenant('')
    }
    onSave?.()
    setAuthByKey((s) => {
      const rest = { ...s }
      delete rest[authKey(b.url, b.tenant)]
      return rest
    })
  }

  return {
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
  }
}