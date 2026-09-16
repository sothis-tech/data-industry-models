/**
 * Detección y limpieza de referencias / suscripciones al borrar una entidad.
 */

export type IncomingRef = {
  entityId: string
  attrName: string
  /** Targets restantes tras quitar `targetId` (vacío → borrar atributo entero). */
  remainingObjects: string[]
  /** Instancia original (para reconstruir PATCH si hace falta). */
  originalInstance: Record<string, unknown>
}

function asObjectId(value: unknown): string | null {
  if (typeof value === 'string' && value.startsWith('urn:ngsi-ld:')) return value
  if (value && typeof value === 'object' && typeof (value as { id?: unknown }).id === 'string') {
    const id = (value as { id: string }).id
    return id.startsWith('urn:ngsi-ld:') ? id : null
  }
  return null
}

function relationshipObjectIds(inst: Record<string, unknown>): string[] {
  if (inst.type !== 'Relationship' || inst.object == null) return []
  const objs = Array.isArray(inst.object) ? inst.object : [inst.object]
  const ids: string[] = []
  for (const o of objs) {
    const id = asObjectId(o)
    if (id) ids.push(id)
  }
  return ids
}

/** Referencias entrantes (Relationship) hacia `targetId` en el conjunto dado. */
export function findIncomingRelationshipRefs(
  entities: Record<string, unknown>[],
  targetId: string,
): IncomingRef[] {
  if (!targetId) return []
  const out: IncomingRef[] = []
  const skip = new Set(['id', 'type', '@context'])

  for (const entity of entities) {
    const entityId = entity.id
    if (typeof entityId !== 'string' || entityId === targetId) continue

    for (const [attrName, raw] of Object.entries(entity)) {
      if (skip.has(attrName) || raw == null) continue
      const instances = Array.isArray(raw) ? raw : [raw]
      for (const inst of instances) {
        if (!inst || typeof inst !== 'object') continue
        const rec = inst as Record<string, unknown>
        const ids = relationshipObjectIds(rec)
        if (!ids.includes(targetId)) continue
        out.push({
          entityId,
          attrName,
          remainingObjects: ids.filter((id) => id !== targetId),
          originalInstance: { ...rec },
        })
      }
    }
  }
  return out
}
