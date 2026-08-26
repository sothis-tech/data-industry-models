import { useCallback, useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { formatAgentConnectStatus, postAgentConnect } from '../api/agentConnect'
import { createRagTenant } from '../api/rag'
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
        const cur = getCurrentBroker()
        if (!cur) return prev
        const key = authKey(cur.url, cur.tenant)
        if (!prev[key]) return prev
        return { ...prev, [key]: false }
      })
    }
    window.addEventListener(ORION_SESSION_LOST, onSessionLost)
    return () => window.removeEventListener(ORION_SESSION_LOST, onSessionLost)
  }, [])

  const persistBrokers = useCallback((list: StoredBroker[]) => {
    setStoredBrokers(list)
    setBrokers(list)
  }, [])

  const upsertBroker = useCallback((broker: StoredBroker): StoredBroker[] => {
    const list = getStoredBrokers()
    const key = authKey(broker.url, broker.tenant)
    const idx = list.findIndex((b) => authKey(b.url, b.tenant) === key)
    const next = idx >= 0
      ? list.map((b, i) => (i === idx ? broker : b))
      : [...list, broker]
    return next
  }, [])

  async function onCheckAndLogin() {
    const url = brokerUrl.trim()
    const tenant = brokerTenant.trim()
    if (!url) {
      setStatus(t('config.broker.status.needUrl'))
      return
    }
    if (!authUsername.trim() || !authPassword) {
      setStatus(t('config.broker.status.needCredentials'))
      return
    }
    setChecking(true)
    setStatus(t('config.broker.status.checking'))
    try {
      const probe = await checkOrionAuth(url, tenant, {
        username: authUsername.trim(),
        password: authPassword,
      })
      if (!probe.ok || probe.data.auth_ok === false) {
        const detail = probe.data.detail ? ` ${probe.data.detail}` : ''
        setStatus(t('config.broker.status.authFailed', { detail }))
        return
      }
      const login = await loginOrion(url, tenant, authUsername.trim(), authPassword)
      if (!login.ok) {
        setStatus(t('config.broker.status.loginFailed', { error: login.error ?? '' }))
        return
      }
      setAuthByKey((prev) => ({ ...prev, [authKey(url, tenant)]: true }))
      setAuthPassword('')

      const name = brokerName.trim() || url
      const broker: StoredBroker = { name, url, tenant: tenant || undefined }
      persistBrokers(upsertBroker(broker))
      setCurrentBroker(broker.name, broker.url, broker.tenant)
      setCurrentUrl(broker.url)
      setCurrentKey(authKey(broker.url, broker.tenant))

      void createRagTenant(tenant).catch(() => {})

      const agentConnect = await postAgentConnect(tenant, url)
      const summary = formatAgentConnectStatus(agentConnect.body)
      setStatus(t('config.broker.status.connected', { summary }))
      onSave?.()
    } catch (e) {
      setStatus(t('config.broker.status.connectError', { error: e instanceof Error ? e.message : String(e) }))
    } finally {
      setChecking(false)
    }
  }

  async function onLogout(broker: StoredBroker) {
    setAuthBusy(true)
    try {
      const res = await logoutOrion(broker.url, broker.tenant)
      setAuthByKey((prev) => ({ ...prev, [authKey(broker.url, broker.tenant)]: false }))
      if (res.ok) {
        setStatus(t('config.broker.status.loggedOut'))
      } else {
        setStatus(t('config.broker.status.logoutFailed', { error: res.error ?? '' }))
      }
    } finally {
      setAuthBusy(false)
    }
  }

  function onSaveBroker() {
    const url = brokerUrl.trim()
    if (!url) {
      setStatus(t('config.broker.status.needUrl'))
      return
    }
    const tenant = brokerTenant.trim()
    const name = brokerName.trim() || url
    const broker: StoredBroker = { name, url, tenant: tenant || undefined }
    persistBrokers(upsertBroker(broker))
    setCurrentBroker(broker.name, broker.url, broker.tenant)
    setCurrentUrl(broker.url)
    setCurrentKey(authKey(broker.url, broker.tenant))
    setStatus(t('config.broker.status.saved', { name }))
    onSave?.()
  }

  function onLoadConnection(broker: StoredBroker) {
    setBrokerName(broker.name)
    setBrokerUrl(broker.url)
    setBrokerTenant(broker.tenant ?? '')
    setCurrentBroker(broker.name, broker.url, broker.tenant)
    setCurrentUrl(broker.url)
    setCurrentKey(authKey(broker.url, broker.tenant))
    setStatus(t('config.broker.status.activeConnection', { name: broker.name }))
    onSave?.()
  }

  function onDeactivate() {
    clearCurrentBroker()
    setCurrentUrl(null)
    setCurrentKey(null)
    setStatus(t('config.broker.status.deactivated'))
    onSave?.()
  }

  function onDelete(broker: StoredBroker) {
    if (!confirm(t('config.broker.status.confirmDelete', { name: broker.name }))) return
    const key = authKey(broker.url, broker.tenant)
    persistBrokers(getStoredBrokers().filter((b) => authKey(b.url, b.tenant) !== key))
    const cur = getCurrentBroker()
    if (cur && authKey(cur.url, cur.tenant) === key) {
      clearCurrentBroker()
      setCurrentUrl(null)
      setCurrentKey(null)
    }
    setStatus(t('config.broker.status.deleted', { name: broker.name }))
    onSave?.()
  }

  return {
    brokerName, setBrokerName,
    brokerUrl, setBrokerUrl,
    brokerTenant, setBrokerTenant,
    brokers,
    currentUrl,
    currentKey,
    status,
    checking,
    authUsername, setAuthUsername,
    authPassword, setAuthPassword,
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
