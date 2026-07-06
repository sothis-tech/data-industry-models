/**
 * Utilidades HTTP genéricas del frontend.
 *
 * - API_BASE: origin de la SPA (el proxy Vite reescribe /api → backend).
 * - readJson: lee el body como texto y lo parsea; si falla, devuelve el
 *   fallback Y registra un log JSON (evento http_read_json_failed).
 * - parseProxyEnvelope: interpreta el sobre estándar { status, body, error }
 *   que devuelve nuestro backend proxy.
 * - networkError: construye un sobre de error cuando fetch lanza (sin red,
 *   timeout, CORS, etc.).
 */

import { log } from './logger'
import { reportOrionAuthFailure } from './orionSessionEvents'

export const API_BASE = window.location.origin

export type ProxyEnvelope<TBody> = {
  status: number
  body: TBody
  error: string | null
}

type ProxyResponse<TBody> = {
  status?: number
  body?: TBody
  error?: string | null
}

export function parseProxyEnvelope<TBody>(
  res: Response,
  data: ProxyResponse<TBody>,
  fallbackBody: TBody,
): ProxyEnvelope<TBody> {
  const status = data.status !== undefined ? data.status : res.status
  const body = data.body !== undefined ? data.body : fallbackBody
  const error = data.error ?? null
  reportOrionAuthFailure(status, data as Record<string, unknown>, error)
  return { status, body, error }
}

/**
 * Lee el body de la respuesta como JSON.
 * A diferencia de `res.json()`, primero captura el texto crudo para que,
 * si el parseo falla (respuesta HTML, vacía, truncada…), el mensaje de
 * aviso incluya los primeros caracteres recibidos — muy útil para depurar
 * errores de proxy/backend sin mirar las DevTools de red.
 */
export async function readJson<T>(res: Response, fallback: T): Promise<T> {
  let raw = ''
  try {
    raw = await res.text()
    return JSON.parse(raw) as T
  } catch (e) {
    const preview = raw.length > 0
      ? `"${raw.slice(0, 150).replace(/\s+/g, ' ').trim()}…"`
      : '(respuesta vacía)'
    log.warn('readJson: respuesta no es JSON válido', {
      event: 'http_read_json_failed',
      url: res.url,
      httpStatus: res.status,
      parseError: String(e),
      bodyPreview: preview,
    })
    return fallback
  }
}

export function networkError<TBody>(
  message: string,
  fallbackBody: TBody,
): ProxyEnvelope<TBody> {
  log.error('fetch falló (red o excepción)', {
    event: 'http_network_error',
    error: message,
  })
  return { status: 0, body: fallbackBody, error: `Sin conexión: ${message}` }
}
