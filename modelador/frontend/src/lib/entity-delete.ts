import {
  deleteEntity,
  deleteEntityAttr,
  deleteSubscription,
  getSubscriptions,
  patchEntityAttrs,
} from '../api/orion'
import { fetchAllOrionEntities } from './orion-entities'
import { findIncomingRelationshipRefs } from './entity-refs'
import { quantumLeapSubscriptionIdsForEntity } from './subscriptions'
import type { NgsiLdEntity } from '../types/entity'

export type DeleteEntityCascadeResult = {
  status: number
  error: string | null
  warnings: string[]
}

/**
 * Limpia suscripciones QL + relaciones entrantes y luego borra la entidad.
 */
export async function deleteEntityCascade(
  brokerBaseUrl: string,
  entityId: string,
  opts: {
    tenant?: string
    /** Si se pasa, se usa para buscar refs entrantes (evita re-fetch). */
    knownEntities?: NgsiLdEntity[] | Record<string, unknown>[]
  } = {},
): Promise<DeleteEntityCascadeResult> {
  const warnings: string[] = []
  const tenant = opts.tenant

  // 1) Suscripciones QL
  const subRes = await getSubscriptions(brokerBaseUrl, { tenant })
  if (subRes.error || subRes.status >= 400) {
    warnings.push(subRes.error ?? `No se pudieron listar suscripciones (${subRes.status})`)
  } else {
    const subIds = quantumLeapSubscriptionIdsForEntity(subRes.body ?? [], entityId)
    for (const sid of subIds) {
      const del = await deleteSubscription(brokerBaseUrl, sid, tenant)
      if (del.error || (del.status !== 0 && del.status >= 400)) {
        warnings.push(del.error ?? `Error borrando suscripción ${sid}`)
      }
    }
  }

  // 2) Relaciones entrantes
  let entities: Record<string, unknown>[] =
    (opts.knownEntities as Record<string, unknown>[] | undefined) ?? []
  if (!entities.length) {
    const fetched = await fetchAllOrionEntities(brokerBaseUrl, { tenant })
    if (fetched.error && !fetched.entities.length) {
      warnings.push(fetched.error)
    } else {
      entities = fetched.entities as unknown as Record<string, unknown>[]
      if (fetched.error) warnings.push(fetched.error)
    }
  }

  const refs = findIncomingRelationshipRefs(entities, entityId)
  for (const ref of refs) {
    if (ref.remainingObjects.length === 0) {
      const del = await deleteEntityAttr(brokerBaseUrl, ref.entityId, ref.attrName, tenant)
      if (del.error || (del.status !== 0 && del.status >= 400)) {
        warnings.push(
          del.error ?? `Error quitando ${ref.attrName} de ${ref.entityId}`,
        )
      }
    } else {
      const patched = {
        ...ref.originalInstance,
        object:
          ref.remainingObjects.length === 1
            ? ref.remainingObjects[0]
            : ref.remainingObjects,
      }
      const patch = await patchEntityAttrs(
        brokerBaseUrl,
        ref.entityId,
        { [ref.attrName]: patched },
        tenant,
      )
      if (patch.error || (patch.status !== 0 && patch.status >= 400)) {
        warnings.push(
          patch.error ?? `Error actualizando ${ref.attrName} en ${ref.entityId}`,
        )
      }
    }
  }

  // 3) Borrar entidad
  const delEntity = await deleteEntity(brokerBaseUrl, entityId, tenant)
  return {
    status: delEntity.status,
    error: delEntity.error,
    warnings,
  }
}
