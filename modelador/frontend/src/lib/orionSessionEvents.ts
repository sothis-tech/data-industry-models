/** Sincroniza el estado global de sesión Orion cuando caduca o falta. */

export const ORION_SESSION_LOST = 'modelador:orion-session-lost'

export type OrionSessionLostDetail = {
  reason?: string
}

export function dispatchOrionSessionLost(reason?: string): void {
  window.dispatchEvent(
    new CustomEvent<OrionSessionLostDetail>(ORION_SESSION_LOST, {
      detail: { reason },
    }),
  )
}

function authMessageFromData(data?: Record<string, unknown>, error?: string | null): string {
  const parts: string[] = []
  if (error) parts.push(error)
  if (typeof data?.error === 'string') parts.push(data.error)
  if (typeof data?.detail === 'string') parts.push(data.detail)
  return parts.join(' ')
}

export function isOrionAuthFailure(
  status: number,
  data?: Record<string, unknown> | null,
  error?: string | null,
): boolean {
  if (status !== 401) return false
  const code = data?.error_code
  if (code === 'orion_token_expired' || code === 'orion_auth_required') return true
  const text = authMessageFromData(data ?? undefined, error)
  return /sesión orion|sesion orion|orion_auth|token_expired|inicia(r)? sesi[oó]n|chat bloqueado|conéctate en configuración|conecta orion/i.test(
    text,
  )
}

/** Llamar tras respuestas BFF/proxy que puedan indicar sesión caducada. */
export function reportOrionAuthFailure(
  status: number,
  data?: unknown,
  error?: string | null,
): void {
  const rec =
    data && typeof data === 'object' && !Array.isArray(data)
      ? (data as Record<string, unknown>)
      : null
  if (!isOrionAuthFailure(status, rec, error)) return
  const reason = error ?? authMessageFromData(rec ?? undefined, error)
  dispatchOrionSessionLost(reason || undefined)
}
