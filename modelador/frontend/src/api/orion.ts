import { API_BASE, networkError, parseProxyEnvelope, readJson } from '../lib/http'
import { reportOrionAuthFailure } from '../lib/orionSessionEvents'
import type { PrepareAttrsResult, PreparePayloadResult } from '../types/entity'

type ApiResult<T> = {
  status: number
  error: string | null
} & T

/** Convierte el campo `detail` de una respuesta de error (string o array Pydantic) en string legible */
function extractDetailMsg(raw: Record<string, unknown>, fallback: string): string {
  const detail = raw.detail
  if (!detail) return fallback
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) {
    return detail
      .map((d: unknown) => {
        if (d && typeof d === 'object' && 'msg' in (d as object)) return String((d as { msg: unknown }).msg)
        return String(d)
      })
      .join('; ')
  }
  return fallback
}

function extractApiError(data: unknown, fallback = 'Error de API'): string {
  if (!data) return fallback
  if (typeof data === 'string') return data

  const record = data as {
    detail?: unknown
    error?: string
    message?: string
  }
  if (Array.isArray(record.detail)) {
    return record.detail
      .map((d) => {
        if (typeof d === 'object' && d && 'msg' in d) {
          return String((d as { msg?: string }).msg || '')
        }
        return JSON.stringify(d)
      })
      .join('; ')
  }
  return String(record.detail || record.error || record.message || fallback)
}

function envelopeStatus(
  data: { status?: number } | null | undefined,
  resStatus: number,
): number {
  return data?.status !== undefined ? data.status : resStatus
}

/** Añade fiware_service a URLSearchParams si tiene valor. */
function withTenant(params: URLSearchParams, tenant?: string): URLSearchParams {
  if (tenant) params.set('fiware_service', tenant)
  return params
}

export async function checkBrokerHealth(
  brokerBaseUrl: string,
  signal?: AbortSignal,
  tenant?: string,
): Promise<{ ok: boolean; status: number; data: Record<string, unknown> }> {
  const params = withTenant(new URLSearchParams({ broker_base_url: brokerBaseUrl }), tenant)
  try {
    const res = await fetch(`${API_BASE}/api/health?${params}`, { signal })
    const data = await readJson<Record<string, unknown>>(res, {})
    return { ok: res.ok && data.ok === true, status: res.status, data }
  } catch (e) {
    if (e instanceof Error && e.name === 'AbortError') {
      return { ok: false, status: 0, data: {} }
    }
    const message = e instanceof Error ? e.message : String(e)
    return { ok: false, status: 0, data: { error: message } }
  }
}

export type OrionAuthProbeResult = {
  connectivity_ok?: boolean
  auth_ok?: boolean | null
  http_status?: number | null
  detail?: string | null
}

export async function checkOrionAuth(
  brokerBaseUrl: string,
  tenant?: string,
  credentials?: { username: string; password: string },
): Promise<{ ok: boolean; data: OrionAuthProbeResult }> {
  try {
    const res = await fetch(`${API_BASE}/api/health/orion`, {
      method: 'POST',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        broker_base_url: brokerBaseUrl.trim(),
        fiware_service: tenant?.trim() || '',
        username: credentials?.username ?? '',
        password: credentials?.password ?? '',
      }),
    })
    const data = await readJson<OrionAuthProbeResult>(res, {})
    return { ok: res.ok && data.connectivity_ok === true && data.auth_ok !== false, data }
  } catch (e) {
    const message = e instanceof Error ? e.message : String(e)
    return { ok: false, data: { connectivity_ok: false, auth_ok: false, detail: message } }
  }
}

export async function loginOrion(
  brokerBaseUrl: string,
  tenant: string | undefined,
  username: string,
  password: string,
): Promise<{ ok: boolean; error?: string }> {
  try {
    const res = await fetch(`${API_BASE}/api/auth/orion/login`, {
      method: 'POST',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        broker_base_url: brokerBaseUrl.trim(),
        fiware_service: tenant?.trim() || '',
        username,
        password,
      }),
    })
    const data = await readJson<Record<string, unknown>>(res, {})
    if (!res.ok) return { ok: false, error: extractApiError(data, 'No se pudo conectar con Keycloak') }
    return { ok: true }
  } catch (e) {
    return { ok: false, error: e instanceof Error ? e.message : String(e) }
  }
}

export async function logoutOrion(
  brokerBaseUrl: string,
  tenant?: string,
): Promise<{ ok: boolean; error?: string }> {
  const params = withTenant(new URLSearchParams({ broker_base_url: brokerBaseUrl.trim() }), tenant)
  try {
    const res = await fetch(`${API_BASE}/api/auth/orion/logout?${params}`, {
      method: 'POST',
      credentials: 'include',
    })
    const data = await readJson<Record<string, unknown>>(res, {})
    if (!res.ok) return { ok: false, error: extractApiError(data, 'No se pudo cerrar sesión') }
    return { ok: true }
  } catch (e) {
    return { ok: false, error: e instanceof Error ? e.message : String(e) }
  }
}

export async function getOrionAuthStatus(
  brokerBaseUrl: string,
  tenant?: string,
): Promise<{ loggedIn: boolean }> {
  const params = withTenant(new URLSearchParams({ broker_base_url: brokerBaseUrl.trim() }), tenant)
  try {
    const res = await fetch(`${API_BASE}/api/auth/orion/status?${params}`, {
      credentials: 'include',
    })
    const data = await readJson<{ logged_in?: boolean }>(res, {})
    return { loggedIn: res.ok && data.logged_in === true }
  } catch {
    return { loggedIn: false }
  }
}

export async function postEntity(
  brokerBaseUrl: string,
  entityPayload: Record<string, unknown>,
  tenant?: string,
): Promise<ApiResult<{ body: Record<string, unknown> }>> {
  const params = withTenant(new URLSearchParams({ broker_base_url: brokerBaseUrl }), tenant)
  try {
    const res = await fetch(`${API_BASE}/api/proxy/entities?${params}`, {
      method: 'POST',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(entityPayload),
    })
    const data = await readJson<Record<string, unknown>>(res, {})
    return parseProxyEnvelope(res, data, data)
    } catch (e) {
    const message = e instanceof Error ? e.message : String(e)
    return networkError(message, {})
  }
}

export async function postSubscription(
  brokerBaseUrl: string,
  subscriptionPayload: Record<string, unknown>,
  tenant?: string,
): Promise<ApiResult<{ body: Record<string, unknown> }>> {
  const params = withTenant(new URLSearchParams({ broker_base_url: brokerBaseUrl }), tenant)
  try {
    const res = await fetch(`${API_BASE}/api/proxy/subscriptions?${params}`, {
      method: 'POST',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(subscriptionPayload),
    })
    const data = await readJson<Record<string, unknown>>(res, {})
    return parseProxyEnvelope(res, data, data)
  } catch (e) {
    const message = e instanceof Error ? e.message : String(e)
    return networkError(message, {})
  }
}

export async function getEntities(

  brokerBaseUrl: string,
  opts: { type?: string; id?: string; limit?: number; offset?: number; tenant?: string } = {},
): Promise<ApiResult<{ body: Record<string, unknown>[] }>> {
  if (!brokerBaseUrl || !brokerBaseUrl.trim()) {
    return { status: 400, body: [], error: 'URL del broker vacía' }
  }
  const params = withTenant(new URLSearchParams({ broker_base_url: brokerBaseUrl.trim() }), opts.tenant)
  if (opts.type) params.set('type', opts.type)
  if (opts.id) params.set('id', opts.id)
  if (opts.limit != null) params.set('limit', String(opts.limit))
  if (opts.offset != null) params.set('offset', String(opts.offset))

  try {
    const res = await fetch(`${API_BASE}/api/proxy/entities?${params}`, { credentials: 'include' })
    const data = await readJson<Record<string, unknown>>(res, {})
    const list =
      data.body != null
        ? data.body
        : Array.isArray(data)
          ? data
          : []
    const body = Array.isArray(list)
      ? (list as Record<string, unknown>[])
      : list && typeof list === 'object' && 'id' in list
        ? [list as Record<string, unknown>]
        : []
    const error =
      data.error && typeof data.error === 'string'
        ? data.error
        : !res.ok
          ? extractApiError(data, 'Error al conectar con Orion')
          : null
    const status = envelopeStatus(data, res.status)
    reportOrionAuthFailure(status, data, error)
    return { status, body, error }
  } catch (e) {
    const message = e instanceof Error ? e.message : String(e)
    return { status: 0, body: [], error: `Sin conexión: ${message}` }
  }
}

export async function getEntityById(
  brokerBaseUrl: string,
  entityId: string,
  tenant?: string,
): Promise<ApiResult<{ body: Record<string, unknown> | null }>> {
  if (!brokerBaseUrl || !entityId) return { status: 400, body: null, error: 'Parámetros requeridos' }
  const params = withTenant(new URLSearchParams({ broker_base_url: brokerBaseUrl.trim() }), tenant)
  try {
    const res = await fetch(`${API_BASE}/api/proxy/entities/${encodeURIComponent(entityId)}?${params}`, {
      credentials: 'include',
    })
    const data = await readJson<Record<string, unknown>>(res, {})
    const status = envelopeStatus(data as { status?: number }, res.status)
    const error = data.error ? String(data.error) : res.ok ? null : extractApiError(data, 'Error obteniendo entidad')
    reportOrionAuthFailure(status, data, error)
    return {
      status,
      body: (data.body as Record<string, unknown>) ?? null,
      error,
    }
  } catch (e) {
    return networkError(e instanceof Error ? e.message : String(e), null)
  }
}

export async function patchEntityAttrs(
  brokerBaseUrl: string,
  entityId: string,
  attrsPayload: Record<string, unknown>,
  tenant?: string,
): Promise<ApiResult<{ body: Record<string, unknown> }>> {
  const params = withTenant(new URLSearchParams({ broker_base_url: brokerBaseUrl.trim() }), tenant)
  try {
    const res = await fetch(
      `${API_BASE}/api/proxy/entities/${encodeURIComponent(entityId)}/attrs?${params}`,
      {
        method: 'PATCH',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(attrsPayload),
      },
    )
    const data = await readJson<Record<string, unknown>>(res, {})
    return parseProxyEnvelope(res, data, data)
  } catch (e) {
    return networkError(e instanceof Error ? e.message : String(e), {})
  }
}

export async function deleteEntity(
  brokerBaseUrl: string,
  entityId: string,
  tenant?: string,
): Promise<ApiResult<{ body: null }>> {
  const params = withTenant(new URLSearchParams({ broker_base_url: brokerBaseUrl.trim() }), tenant)
  try {
    const res = await fetch(
      `${API_BASE}/api/proxy/entities/${encodeURIComponent(entityId)}?${params}`,
      { method: 'DELETE', credentials: 'include' },
    )
    const data = await readJson<Record<string, unknown>>(res, {})
    return {
      status: envelopeStatus(data as { status?: number }, res.status),
      body: null,
      error: res.ok ? null : extractApiError(data, 'Error eliminando entidad'),
    }
  } catch (e) {
    return networkError(e instanceof Error ? e.message : String(e), null)
  }
}

export async function prepareEntityPayload(
  payload: Record<string, unknown>,
  type: string,
  defaultContext: unknown,
): Promise<PreparePayloadResult> {
  try {
    const res = await fetch(`${API_BASE}/api/entities/prepare-payload`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ payload, type, default_context: defaultContext }),
    })
    // El backend devuelve snake_case: payload_for_validation, payload_to_send, input_mode
    const raw = await res.json().catch(() => ({})) as Record<string, unknown>
    if (!res.ok) {
      return { error: extractDetailMsg(raw, 'Error preparando payload'), inputMode: 'plain', payloadForValidation: {}, payloadToSend: {} }
    }
    return {
      error: null,
      inputMode: (raw.input_mode as 'plain' | 'normalized') ?? 'plain',
      payloadForValidation: (raw.payload_for_validation as Record<string, unknown>) ?? {},
      payloadToSend: (raw.payload_to_send as Record<string, unknown>) ?? {},
    }
  } catch (e) {
    return { error: 'Sin conexión: ' + String(e), inputMode: 'plain', payloadForValidation: {}, payloadToSend: {} }
  }
}

export async function prepareAttrsPayload(
  attrsPayload: Record<string, unknown>,
): Promise<PrepareAttrsResult> {
  try {
    const res = await fetch(`${API_BASE}/api/entities/prepare-attrs-payload`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ attrs_payload: attrsPayload }),
    })
    // El backend devuelve snake_case: attrs_payload_to_send
    const raw = await res.json().catch(() => ({})) as Record<string, unknown>
    if (!res.ok) {
      return { error: extractDetailMsg(raw, 'Error preparando atributos'), attrsPayloadToSend: {} }
    }
    return {
      error: null,
      attrsPayloadToSend: (raw.attrs_payload_to_send as Record<string, unknown>) ?? {},
    }
  } catch (e) {
    return { error: 'Sin conexión: ' + String(e), attrsPayloadToSend: {} }
  }
}
