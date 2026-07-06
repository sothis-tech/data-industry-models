import { API_BASE } from '../lib/http'
import { log } from '../lib/logger'
import type { Relationship } from '../lib/model-parser'
import type { NgsiLdEntity } from '../types/entity'
import type { EntityView, OrionGraphData, SchemaGraphData, SchemaTypeView } from '../types/graph'

type GraphResult<T> = T & { error?: string }

export async function buildSchemaGraph(
  types: string[],
  relationships: Relationship[],
): Promise<GraphResult<SchemaGraphData>> {
  try {
    const res = await fetch(`${API_BASE}/api/graph/schema/build`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ types, relationships }),
    })
    const data = (await res.json().catch(() => ({}))) as SchemaGraphData & {
      error?: string
      detail?: string
    }
    if (!res.ok) {
      const err = data.detail ?? data.error ?? 'Error construyendo grafo de modelo'
      log.warn('buildSchemaGraph: respuesta no OK', {
        event: 'graph_schema_build_http_error',
        httpStatus: res.status,
        error: err,
      })
      return { nodes: [], links: [], error: err }
    }
    return data
  } catch (e) {
    log.error('buildSchemaGraph: excepción', {
      event: 'graph_schema_build_failed',
      error: String(e),
    })
    return { nodes: [], links: [], error: 'Sin conexión: ' + String(e) }
  }
}

export async function buildSchemaTypeView(
  typeId: string,
  relationships: Relationship[],
): Promise<{ view: SchemaTypeView | null; error?: string }> {
  try {
    const res = await fetch(`${API_BASE}/api/graph/schema/type-view`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ type_id: typeId, relationships }),
    })
    const data = (await res.json().catch(() => ({}))) as {
      view?: SchemaTypeView
      error?: string
      detail?: string
    }
    if (!res.ok) {
      const err = data.detail ?? data.error ?? 'Error obteniendo vista de tipo'
      log.warn('buildSchemaTypeView: respuesta no OK', {
        event: 'graph_type_view_http_error',
        httpStatus: res.status,
        error: err,
      })
      return { view: null, error: err }
    }
    return { view: data.view ?? null, error: data.error }
  } catch (e) {
    log.error('buildSchemaTypeView: excepción', {
      event: 'graph_type_view_failed',
      error: String(e),
    })
    return { view: null, error: 'Sin conexión: ' + String(e) }
  }
}

export async function buildOrionGraph(
  entities: NgsiLdEntity[],
  relationships: Relationship[],
): Promise<GraphResult<OrionGraphData>> {
  try {
    const res = await fetch(`${API_BASE}/api/graph/orion/build`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ entities, relationships }),
    })
    const data = (await res.json().catch(() => ({}))) as OrionGraphData & {
      error?: string
      detail?: string
    }
    if (!res.ok) {
      const err = data.detail ?? data.error ?? 'Error construyendo grafo Orion'
      log.warn('buildOrionGraph: respuesta no OK', {
        event: 'graph_orion_build_http_error',
        httpStatus: res.status,
        error: err,
      })
      return { nodes: [], links: [], error: err }
    }
    return data
  } catch (e) {
    log.error('buildOrionGraph: excepción', {
      event: 'graph_orion_build_failed',
      error: String(e),
    })
    return { nodes: [], links: [], error: 'Sin conexión: ' + String(e) }
  }
}

export async function getEntityView(
  brokerBaseUrl: string,
  entityId: string,
  tenant?: string,
): Promise<{ view: EntityView | null; error?: string }> {
  const params = new URLSearchParams({ broker_base_url: brokerBaseUrl.trim() })
  if (tenant?.trim()) params.set('fiware_service', tenant.trim())
  try {
    const res = await fetch(`${API_BASE}/api/entities/${encodeURIComponent(entityId)}/view?${params}`, {
      credentials: 'include',
    })
    const data = (await res.json().catch(() => ({}))) as {
      view?: EntityView
      error?: string
      detail?: string
    }
    if (!res.ok) {
      const err = data.detail ?? data.error ?? 'Error obteniendo vista de entidad'
      log.warn('getEntityView: respuesta no OK', {
        event: 'graph_entity_view_http_error',
        httpStatus: res.status,
        error: err,
      })
      return { view: null, error: err }
    }
    return { view: data.view ?? null, error: data.error }
  } catch (e) {
    log.error('getEntityView: excepción', {
      event: 'graph_entity_view_failed',
      error: String(e),
    })
    return { view: null, error: 'Sin conexión: ' + String(e) }
  }
}
