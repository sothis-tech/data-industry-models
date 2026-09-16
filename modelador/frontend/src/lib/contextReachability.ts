/**
 * Comprobación de alcanzabilidad de la URL de @context del modelo.
 * Usa el proxy del backend para que hostnames Docker (context-server) resuelvan.
 */
import { useCallback, useEffect, useState } from 'react'
import { fetchViaProxy } from '../api/model'
import i18n from './i18n'
import { getModelJson } from './modelStore'

export type ContextReachability = 'unknown' | 'ok' | 'unreachable' | 'none'

const POLL_MS = 60_000

export function readModelContextUrl(modelJson: string | null): string | null {
  if (!modelJson) return null
  try {
    const m = JSON.parse(modelJson) as { contextUrl?: unknown }
    return typeof m.contextUrl === 'string' && m.contextUrl.trim() ? m.contextUrl.trim() : null
  } catch {
    return null
  }
}

export async function probeContextUrl(url: string): Promise<boolean> {
  try {
    await fetchViaProxy(url)
    return true
  } catch {
    return false
  }
}

/**
 * Hook: comprueba contextUrl del modelo activo al montar, al cambiar la URL,
 * al volver a la pestaña y cada 60s mientras esté visible.
 */
export function useContextReachability(modelJson: string | null): ContextReachability {
  const url = readModelContextUrl(modelJson)
  const [state, setState] = useState<ContextReachability>(url ? 'unknown' : 'none')

  const check = useCallback(async (target: string | null) => {
    if (!target) {
      setState('none')
      return
    }
    setState((prev) => (prev === 'ok' || prev === 'unreachable' ? prev : 'unknown'))
    const ok = await probeContextUrl(target)
    setState(ok ? 'ok' : 'unreachable')
  }, [])

  useEffect(() => {
    void check(url)
  }, [url, check])

  useEffect(() => {
    function onVisible() {
      if (document.visibilityState === 'visible') void check(url)
    }
    document.addEventListener('visibilitychange', onVisible)
    window.addEventListener('focus', onVisible)
    return () => {
      document.removeEventListener('visibilitychange', onVisible)
      window.removeEventListener('focus', onVisible)
    }
  }, [url, check])

  useEffect(() => {
    if (!url) return undefined
    const id = window.setInterval(() => {
      if (document.visibilityState === 'visible') void check(url)
    }, POLL_MS)
    return () => window.clearInterval(id)
  }, [url, check])

  return state
}

/** Lanza si hay contextUrl y no es alcanzable. Para crear/guardar entidades. */
export async function assertContextReachable(modelJson?: string | null): Promise<void> {
  const raw = modelJson ?? getModelJson()
  const url = readModelContextUrl(raw)
  if (!url) return
  const ok = await probeContextUrl(url)
  if (!ok) {
    throw new Error(i18n.t('errors.context.unreachable', { url }))
  }
}
