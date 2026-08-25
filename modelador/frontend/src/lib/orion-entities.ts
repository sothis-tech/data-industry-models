import i18n from '../lib/i18n'
import { getEntities } from '../api/orion'
import type { NgsiLdEntity } from '../types/entity'
/** Tamaño de página alineado con NGSI-LD / lista de Entidades. */
export const ORION_ENTITIES_PAGE_SIZE = 500
export function uniqueEntitiesById(items: NgsiLdEntity[]): NgsiLdEntity[] {
  const map = new Map<string, NgsiLdEntity>()
  for (const item of items) {
    if (item?.id) map.set(item.id, item)
  }
  return [...map.values()]
}
export type OrionEntitiesPageResult = {
  entities: NgsiLdEntity[]
  error: string | null
  hasMore: boolean
}
export type FetchAllOrionProgress = (loaded: number) => void
export type FetchAllOrionResult = {
  entities: NgsiLdEntity[]
  error: string | null
}
/** Una página de instancias Orion (limit + offset). */
export async function fetchOrionEntitiesPage(
  brokerUrl: string,
  opts: { offset?: number; type?: string; tenant?: string } = {},
): Promise<OrionEntitiesPageResult> {
  const offset = opts.offset ?? 0
  const { body, error } = await getEntities(brokerUrl, {
    limit: ORION_ENTITIES_PAGE_SIZE,
    offset,
    type: opts.type,
    tenant: opts.tenant,
  })
  if (error) {
    return { entities: [], error, hasMore: false }
  }
  const entities = (body ?? []) as NgsiLdEntity[]
  return {
    entities,
    error: null,
    hasMore: entities.length === ORION_ENTITIES_PAGE_SIZE,
  }
}
/**
 * Recorre todas las páginas hasta agotar el broker (modelador: conjunto completo).
 * Si hay error a mitad de camino, devuelve lo acumulado y el error.
 */
export async function fetchAllOrionEntities(
  brokerUrl: string,
  opts: { type?: string; tenant?: string; onProgress?: FetchAllOrionProgress } = {},
): Promise<FetchAllOrionResult> {
  const batch: NgsiLdEntity[] = []
  let offset = 0
  while (true) {
    const page = await fetchOrionEntitiesPage(brokerUrl, {
      offset,
      type: opts.type,
      tenant: opts.tenant,
    })
    if (page.error) {
      return { entities: uniqueEntitiesById(batch), error: page.error }
    }
    if (page.entities.length > 0) {
      batch.push(...page.entities)
      opts.onProgress?.(batch.length)
    }
    if (!page.hasMore || page.entities.length === 0) break
    offset += page.entities.length
  }
  return { entities: uniqueEntitiesById(batch), error: null }
}
/** Varias consultas por tipo (fallback cuando la query global falla). */
export async function fetchAllOrionEntitiesByTypes(
  brokerUrl: string,
  typeUris: string[],
  opts: { tenant?: string; onProgress?: FetchAllOrionProgress } = {},
): Promise<FetchAllOrionResult> {
  if (!typeUris.length) {
    return { entities: [], error: i18n.t('errors.orion.noModelTypes') }
  }
  const chunks: NgsiLdEntity[] = []
  let lastError: string | null = null
  for (const typeUri of typeUris) {
    const { entities, error } = await fetchAllOrionEntities(brokerUrl, {
      type: typeUri,
      tenant: opts.tenant,
    })
    if (error) lastError = error
    if (entities.length) chunks.push(...entities)
    opts.onProgress?.(chunks.length)
  }
  const merged = uniqueEntitiesById(chunks)
  if (!merged.length && lastError) {
    return { entities: [], error: lastError }
  }
  return { entities: merged, error: lastError }
}
