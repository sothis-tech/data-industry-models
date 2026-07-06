import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { getOrionAuthStatus } from '../api/orion'
import { ORION_SESSION_LOST } from '../lib/orionSessionEvents'
import { getCurrentBroker } from '../lib/storage'
import type { StoredBroker } from '../types/broker'

/** Revalidar sesión al volver a la pestaña y de forma periódica (tokens Keycloak). */
const SESSION_POLL_MS = 90_000

export type BrokerHealthState = 'unknown' | 'ok' | 'no-session' | 'error'

export type ModelSummary = {
  label: string
  loaded: boolean
}

function readModelSummary(): ModelSummary {
  try {
    const raw = localStorage.getItem('ngsi_model')
    if (!raw) return { label: '', loaded: false }
    const m = JSON.parse(raw) as {
      schemas?: unknown[]
      context?: unknown
    }
    const cnt = (m.schemas ?? []).length
    if (cnt > 0) return { label: `${cnt} tipos`, loaded: true }
    if (m.context) return { label: 'contexto cargado', loaded: true }
    return { label: '', loaded: false }
  } catch {
    return { label: '', loaded: false }
  }
}

export function useAppStatus(refreshKey = 0) {
  // Leer localStorage en cada render derivado de refreshKey (no en efecto).
  const broker = useMemo<StoredBroker | null>(
    () => getCurrentBroker(),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [refreshKey],
  )

  const model = useMemo<ModelSummary>(
    () => readModelSummary(),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [refreshKey],
  )

  const [health, setHealth] = useState<BrokerHealthState>('unknown')
  const abortRef = useRef<AbortController | null>(null)

  const refreshSessionHealth = useCallback(() => {
    if (abortRef.current) abortRef.current.abort()

    if (!broker) {
      setHealth('unknown')
      return
    }

    const ctrl = new AbortController()
    abortRef.current = ctrl

    getOrionAuthStatus(broker.url, broker.tenant)
      .then(({ loggedIn }) => {
        if (ctrl.signal.aborted) return
        setHealth(loggedIn ? 'ok' : 'no-session')
      })
      .catch(() => {
        if (ctrl.signal.aborted) return
        setHealth('error')
      })
  }, [broker])

  useEffect(() => {
    refreshSessionHealth()
    return () => abortRef.current?.abort()
  }, [refreshSessionHealth])

  useEffect(() => {
    function onSessionLost() {
      setHealth('no-session')
    }
    window.addEventListener(ORION_SESSION_LOST, onSessionLost)
    return () => window.removeEventListener(ORION_SESSION_LOST, onSessionLost)
  }, [])

  useEffect(() => {
    function onVisible() {
      if (document.visibilityState === 'visible') refreshSessionHealth()
    }
    document.addEventListener('visibilitychange', onVisible)
    window.addEventListener('focus', onVisible)
    return () => {
      document.removeEventListener('visibilitychange', onVisible)
      window.removeEventListener('focus', onVisible)
    }
  }, [refreshSessionHealth])

  useEffect(() => {
    if (!broker) return undefined
    const id = window.setInterval(refreshSessionHealth, SESSION_POLL_MS)
    return () => window.clearInterval(id)
  }, [broker, refreshSessionHealth])

  return { broker, health, model }
}
