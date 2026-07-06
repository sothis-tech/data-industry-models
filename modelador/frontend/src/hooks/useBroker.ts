import { useCallback, useEffect, useState } from 'react'
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
      setStatus('Indica la URL base de Kong.')
      return
    }
    if (!tenant) {
      setStatus('Indica el tenant de la conexión Orion.')
      return
    }
    setBrokerName(name)
    setBrokerUrl(url)
    setBrokerTenant(tenant)
    setChecking(true)
    setAuthBusy(true)
    setStatus('Comprobando credenciales y conexión...')
    const username = authUsername.trim()
    if (!username || !authPassword) {
      setStatus('Introduce usuario y contraseña para conectar.')
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

        const agentConnect = await postAgentConnect(tenant, url)
        if (agentConnect.error || agentConnect.status >= 400) {
          void createRagTenant(tenant).catch(() => {})
          setStatus(
            `Conexión Orion iniciada: ${name}. Aviso: el agente LLM no se preparó (${agentConnect.error ?? `HTTP ${agentConnect.status}`}).`,
          )
        } else {
          const summary = formatAgentConnectStatus(agentConnect.body)
          setStatus(`Conexión Orion iniciada: ${name}. Agente: ${summary}.`)
        }
      } else {
        setStatus(`No se pudo iniciar sesión: ${login.error ?? 'credenciales no válidas'}`)
      }
    } else {
      const err =
        (typeof data.detail === 'string' && data.detail) ||
        ('error' in data && typeof data.error === 'string' && data.error) ||
        'Comprueba la URL de Kong, el tenant y las credenciales.'
      setStatus(`No se pudo conectar: ${err}`)
    }
    setChecking(false)
    setAuthBusy(false)
  }

  function onSaveBroker() {
    const url = brokerUrl.trim()
    const name = brokerName.trim() || url
    const tenant = brokerTenant.trim() || undefined
    if (!url) {
      setStatus('Indica la URL base de Kong.')
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
    setStatus('Conexión Orion guardada y seleccionada.')
    onSave?.()
    if (tenant) {
      void createRagTenant(tenant).catch(() => {
        setStatus(
          'Conexión guardada. No se pudo asegurar el espacio RAG (¿servicio RAG caído?); inténtalo al abrir documentación.',
        )
      })
    }
  }

  function onLoadConnection(b: StoredBroker) {
    setBrokerName(b.name)
    setBrokerUrl(b.url)
    setBrokerTenant(b.tenant ?? '')
    setAuthPassword('')
    setStatus(`Conexión Orion cargada: ${b.name}. Introduce credenciales y pulsa Conectar.`)
    const t = b.tenant?.trim()
    if (t) {
      void createRagTenant(t).catch(() => {
        setStatus(`Conexión cargada. Aviso: no se pudo asegurar el espacio RAG para "${t}".`)
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
      setStatus('Sesión de la conexión Orion cerrada.')
    } else {
      setStatus(`No se pudo cerrar sesión: ${res.error ?? 'error desconocido'}`)
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
    setStatus('Conexión Orion activa desactivada.')
  }

  function onDelete(b: StoredBroker) {
    const next = brokers.filter((x) => authKey(x.url, x.tenant) !== authKey(b.url, b.tenant))
    setStoredBrokers(next)
    setBrokers(next)
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
    setStatus(`Conexión Orion "${b.name}" eliminada.`)
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
