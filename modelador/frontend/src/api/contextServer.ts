/**
 * Cliente del servidor de contexto multi-tenant (vía proxy del backend).
 *
 * El servidor de contexto almacena el modelo NGSI (schemas, contexto JSON-LD,
 * descriptor y ejemplos) de cada tenant en carpetas. Es la fuente de verdad
 * del modelo cuando hay una conexión Orion con tenant activa.
 */
import { API_BASE, readJson } from '../lib/http'
import i18n from '../lib/i18n'
import type { NgsiModel } from '../types/model'

export type StoredModel = Pick<
  NgsiModel,
  'schemas' | 'context' | 'descriptor' | 'examples' | 'packageName' | 'contextUrl'
>

export type ContextServerConfig = {
  enabled: boolean
  publicBaseUrl: string
}

export async function getContextServerConfig(): Promise<ContextServerConfig> {
  const res = await fetch(`${API_BASE}/api/context-server/config`)
  return readJson<ContextServerConfig>(res, {
    enabled: false,
    publicBaseUrl: 'http://context-server:8090',
  })
}

export async function createContextTenant(name: string): Promise<void> {
  const res = await fetch(`${API_BASE}/api/context-server/tenants`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name }),
  })
  if (!res.ok) throw new Error(i18n.t('errors.contextServer.createTenant', { status: res.status }))
}

export async function deleteContextTenant(tenant: string): Promise<void> {
  const res = await fetch(
    `${API_BASE}/api/context-server/tenants/${encodeURIComponent(tenant)}`,
    { method: 'DELETE' },
  )
  if (!res.ok) throw new Error(i18n.t('errors.contextServer.deleteTenant', { status: res.status }))
}

/** Modelo del tenant, o null si el tenant no existe todavía en el servidor. */
export async function getTenantModel(tenant: string): Promise<StoredModel | null> {
  const res = await fetch(
    `${API_BASE}/api/context-server/tenants/${encodeURIComponent(tenant)}/model`,
  )
  if (res.status === 404) return null
  if (!res.ok) throw new Error(i18n.t('errors.contextServer.getModel', { status: res.status }))
  return readJson<StoredModel | null>(res, null)
}

export async function saveTenantModel(tenant: string, model: StoredModel): Promise<void> {
  const res = await fetch(
    `${API_BASE}/api/context-server/tenants/${encodeURIComponent(tenant)}/model`,
    {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(model),
    },
  )
  if (!res.ok) throw new Error(i18n.t('errors.contextServer.saveModel', { status: res.status }))
}

export async function clearTenantModel(tenant: string): Promise<void> {
  const res = await fetch(
    `${API_BASE}/api/context-server/tenants/${encodeURIComponent(tenant)}/model`,
    { method: 'DELETE' },
  )
  if (!res.ok && res.status !== 404) {
    throw new Error(i18n.t('errors.contextServer.clearModel', { status: res.status }))
  }
}