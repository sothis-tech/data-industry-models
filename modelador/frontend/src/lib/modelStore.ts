/**
 * Almacén centralizado del modelo NGSI (schemas, contexto, descriptor, ejemplos).
 *
 * Fuente de verdad según el estado de la conexión:
 * - Con tenant activo → servidor de contexto (data_space/context_server),
 *   con caché en memoria para lecturas síncronas de los consumidores.
 * - Sin tenant → localStorage (clave legacy 'ngsi_model'), igual que antes.
 *
 * La primera vez que se conecta un tenant sin modelo en el servidor, si existe
 * un modelo legacy en localStorage se migra automáticamente al servidor.
 *
 * Todos los consumidores deben leer el modelo a través de este módulo
 * (useModelJson / getModelJson), nunca de localStorage directamente.
 */
import { useSyncExternalStore } from 'react'
import { getTenantModel, saveTenantModel, type StoredModel } from '../api/contextServer'
import { log } from './logger'
import { getCurrentBroker } from './storage'
import type { NgsiModel } from '../types/model'

const LEGACY_MODEL_KEY = 'ngsi_model'

let cachedJson: string | null = null
let cachedTenant: string | null = null

const listeners = new Set<() => void>()

function notify(): void {
  for (const fn of listeners) fn()
}

export function subscribe(fn: () => void): () => void {
  listeners.add(fn)
  return () => listeners.delete(fn)
}

/** Tenant de la conexión Orion activa, si lo hay. */
export function activeTenant(): string | null {
  return getCurrentBroker()?.tenant?.trim() || null
}

function readLegacy(): string | null {
  try {
    return localStorage.getItem(LEGACY_MODEL_KEY)
  } catch {
    return null
  }
}

/**
 * Modelo actual como JSON string (formato NgsiModel), o null si no hay modelo.
 * Lectura síncrona: con tenant devuelve la caché en memoria (poblada por
 * refreshModelFromServer); sin tenant lee el localStorage legacy.
 */
export function getModelJson(): string | null {
  const tenant = activeTenant()
  if (!tenant) return readLegacy()
  return tenant === cachedTenant ? cachedJson : null
}

function hasContent(model: StoredModel | null): boolean {
  if (!model) return false
  return (model.schemas?.length ?? 0) > 0 || !!model.context || !!model.descriptor
}

/**
 * Sincroniza la caché con el servidor de contexto para el tenant activo.
 * Si el servidor no tiene modelo pero hay uno legacy en localStorage,
 * lo migra (una sola vez) y elimina la clave legacy.
 */
export async function refreshModelFromServer(): Promise<void> {
  const tenant = activeTenant()
  if (!tenant) {
    notify()
    return
  }
  try {
    const model = await getTenantModel(tenant)
    if (!hasContent(model)) {
      const migrated = await migrateLegacyModel(tenant)
      if (!migrated) {
        cachedJson = null
        cachedTenant = tenant
        notify()
      }
      return
    }
    cachedJson = JSON.stringify(model)
    cachedTenant = tenant
    notify()
  } catch (e) {
    log.warn('No se pudo sincronizar el modelo con el servidor de contexto', {
      event: 'model_store_refresh_failed',
      tenant,
      error: e instanceof Error ? e.message : String(e),
    })
    notify()
  }
}

async function migrateLegacyModel(tenant: string): Promise<boolean> {
  const legacy = readLegacy()
  if (!legacy) return false
  try {
    const parsed = JSON.parse(legacy) as Partial<NgsiModel>
    const model: StoredModel = {
      schemas: parsed.schemas ?? [],
      context: parsed.context ?? null,
      descriptor: parsed.descriptor ?? null,
      examples: parsed.examples ?? {},
      packageName: parsed.packageName,
      contextUrl: parsed.contextUrl ?? null,
    }
    if (!hasContent(model)) return false
    await saveTenantModel(tenant, model)
    localStorage.removeItem(LEGACY_MODEL_KEY)
    cachedJson = JSON.stringify(parsed)
    cachedTenant = tenant
    notify()
    log.info('Modelo legacy migrado al servidor de contexto', {
      event: 'model_store_legacy_migrated',
      tenant,
    })
    return true
  } catch (e) {
    log.warn('No se pudo migrar el modelo legacy al servidor de contexto', {
      event: 'model_store_migration_failed',
      tenant,
      error: e instanceof Error ? e.message : String(e),
    })
    return false
  }
}

/**
 * Actualiza el modelo local tras guardarlo o borrarlo.
 * Con tenant activo actualiza la caché en memoria (la persistencia en el
 * servidor la hace el llamante); sin tenant escribe el localStorage legacy.
 */
export function setModelJson(json: string | null): void {
  const tenant = activeTenant()
  if (tenant) {
    cachedTenant = tenant
    cachedJson = json
  } else {
    try {
      if (json === null) localStorage.removeItem(LEGACY_MODEL_KEY)
      else localStorage.setItem(LEGACY_MODEL_KEY, json)
    } catch {
      /* localStorage no disponible */
    }
  }
  notify()
}

/** Hook de React: modelo actual como JSON string, re-renderiza al cambiar. */
export function useModelJson(): string | null {
  return useSyncExternalStore(subscribe, getModelJson)
}
