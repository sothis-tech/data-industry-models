/**
 * URL del WebSocket del voice-agent.
 *
 * Por defecto usa el **mismo host y puerto que la página** + ruta `/api/aea/ws`.
 * Así basta con reenviar un solo puerto (p. ej. SSH `-L 8844:localhost:8844`):
 * el backend del modelador hace de proxy hacia el voice-agent (ver AEA_WS_BACKEND_URL).
 *
 * Si el backend devuelve `AEA_WS_URL` no vacía, se respeta (conexión directa al AEA).
 */
export function resolveAeaWebSocketUrl(
  serverUrl: string | undefined,
  brokerBaseUrl?: string,
  tenant?: string,
): string {
  const trimmed = (serverUrl ?? '').trim()
  if (trimmed) return trimmed

  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  const params = new URLSearchParams()
  if (brokerBaseUrl) params.set('broker_base_url', brokerBaseUrl)
  if (tenant) params.set('tenant', tenant)
  const query = params.toString()
  return `${protocol}//${window.location.host}/api/aea/ws${query ? `?${query}` : ''}`
}
