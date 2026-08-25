import { useCallback, useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import {
  checkOrionAuth,
  getOrionAuthStatus,
  loginOrion,
  logoutOrion,
} from '../api/orion'
import {
  addBroker,
  getBrokers,
  getCurrentBroker,
  removeBroker,
  setCurrentBroker,
  clearCurrentBroker,
} from '../lib/storage'
import type { StoredBroker } from '../types/broker'

export function useBroker(onSave?: () => void) {
  const { t } = useTranslation()
  const [brokerName, setBrokerName] = useState('')
  const [brokerUrl, setBrokerUrl] = useState('')
  const [brokerTenant, setBrokerTenant] = useState('')
  const [brokers, setBrokers] = useState<StoredBroker[]>([])
  const [currentUrl, setCurrentUrl] = useState<string | null>(null)
  const [currentKey, setCurrentKey] = useState<string | null>(null)
  const [status, setStatus] = useState('')
  const [checking, setChecking] = useState(false)
  const [authUsername, setAuthUsername] = useState('')
  const [authPassword, setAuthPassword] = useState('')
  const [authBusy, setAuthBusy] = useState(false)
  const [authByKey, setAuthByKey] = useState<Record<string, boolean>>({})

  const authKey = useCallback((url: string, tenant?: string) => `${url}\u0000${tenant ?? ''}`, [])

  const refreshBrokers = useCallback(() => {
    const list = getBrokers()
    setBrokers(list)
    const current = getCurrentBroker()
    setCurrentUrl(current?.url ?? null)
    setCurrentKey(current ? authKey(current.url, current.tenant) : null)
  }, [authKey])

  useEffect(() => {
    refreshBrokers()
  }, [refreshBrokers])

  useEffect(() => {
    let cancelled = false
    async function probeAll() {
      const list = getBrokers()
      const entries = await Promise.all(
        list.map(async (b) => {
          const { loggedIn } = await getOrionAuthStatus(b.url, b.tenant)
          return [authKey(b.url, b.tenant), loggedIn] as const
        }),
      )
      if (!cancelled) setAuthByKey(Object.fromEntries(entries))
    }
    void probeAll()
    return () => { cancelled = true }
  }, [authKey])

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
      const probe = await checkOrionAuth(url, tenant, { username: authUsername.trim(), password: authPassword })
      if (!probe.ok) {
        const detail = probe.data.detail ?? ''
        setStatus(t('config.broker.status.authFailed', { detail }))
        return
      }
      const login = await loginOrion(url, tenant, authUsername.trim(), authPassword)
      if (!login.ok) {
        setStatus(t('config.broker.status.loginFailed', { error: login.error ?? '' }))
        return
      }
      setAuthPassword('')
      setAuthByKey((prev) => ({ ...prev, [authKey(url, tenant)]: true }))
      setStatus(t('config.broker.status.connected'))
      refreshBrokers()
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
      setStatus(res.ok ? t('config.broker.status.loggedOut') : t('config.broker.status.logoutFailed', { error: res.error ?? '' }))
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
    const name = brokerName.trim() || url
    const tenant = brokerTenant.trim() || undefined
    addBroker({ name, url, tenant })
    setStatus(t('config.broker.status.saved', { name }))
    refreshBrokers()
    onSave?.()
  }

  function onLoadConnection(broker: StoredBroker) {
    setBrokerName(broker.name)
    setBrokerUrl(broker.url)
    setBrokerTenant(broker.tenant ?? '')
    setCurrentBroker(broker)
    setStatus(t('config.broker.status.activeConnection', { name: broker.name }))
    refreshBrokers()
    onSave?.()
  }

  function onDeactivate() {
    clearCurrentBroker()
    setStatus(t('config.broker.status.deactivated'))
    refreshBrokers()
    onSave?.()
  }

  function onDelete(broker: StoredBroker) {
    if (!confirm(t('config.broker.status.confirmDelete', { name: broker.name }))) return
    removeBroker(broker.url, broker.tenant)
    setStatus(t('config.broker.status.deleted', { name: broker.name }))
    refreshBrokers()
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
