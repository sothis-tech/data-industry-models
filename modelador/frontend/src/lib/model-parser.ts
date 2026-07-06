/**
 * Parser del modelo NGSI-LD (schemas, contexto, descriptor, ejemplos).
 * Puerto TypeScript de static/js/model-parser.js.
 */

type ContextItem = string | Record<string, unknown>
type ContextValue = ContextItem | ContextItem[]

export type Relationship = {
  from: string
  property: string
  to: string
  cardinality?: string | null
  description?: string | null
  implicit?: boolean
}

export type ParsedModel = {
  types: string[]
  relationships: Relationship[]
}

function normalizeSchemaTitle(title: unknown): string | null {
  if (!title || typeof title !== 'string') return null
  const part = title.split(/\s*[([]/ )[0].trim()
  return part || null
}

function getTypesFromDescriptor(descriptor: unknown): Set<string> {
  const types = new Set<string>()
  if (!descriptor || !Array.isArray((descriptor as { relationships?: unknown[] }).relationships)) return types
  ;(descriptor as { relationships: { sourceType?: string; targetType?: string }[] }).relationships.forEach(rel => {
    if (rel.sourceType) types.add(rel.sourceType)
    if (rel.targetType) types.add(rel.targetType)
  })
  return types
}

function getTypesFromContext(context: unknown): Set<string> {
  const types = new Set<string>()
  if (!context) return types
  let obj: unknown = context
  if (Array.isArray(obj)) {
    obj = obj.find(item => item && typeof item === 'object' && !Array.isArray(item)) ?? {}
  }
  if (typeof obj !== 'object' || obj === null) return types
  const rec = obj as Record<string, unknown>
  if (rec['@context']) obj = rec['@context']
  if (Array.isArray(obj)) obj = (obj as unknown[]).find(item => item && typeof item === 'object') ?? {}
  if (typeof obj !== 'object') return types
  Object.keys(obj as object).forEach(key => {
    if (/^[A-Z][a-zA-Z0-9]*$/.test(key)) types.add(key)
  })
  return types
}

function getTypesFromSchemas(schemas: unknown[]): Set<string> {
  const types = new Set<string>()
  if (!Array.isArray(schemas)) return types
  schemas.forEach(s => {
    const rec = s as Record<string, unknown>
    const name =
      normalizeSchemaTitle(rec.title) ??
      (rec.$id && typeof rec.$id === 'string' ? rec.$id.split('/').pop()!.replace(/\.json$/, '') : null)
    if (name) types.add(name)
  })
  return types
}

function getRelationshipsFromDescriptor(descriptor: unknown): Relationship[] {
  if (!descriptor) return []
  const d = descriptor as { relationships?: { sourceType?: string; targetType?: string; property?: string; cardinality?: string; description?: string }[] }
  if (!Array.isArray(d.relationships)) return []
  return d.relationships
    .map(rel => ({
      from: rel.sourceType ?? '',
      property: rel.property ?? '',
      to: rel.targetType ?? '',
      cardinality: rel.cardinality ?? null,
      description: rel.description ?? null,
    }))
    .filter(r => r.from && r.to)
}

function getRelationshipsFromExamples(
  examples: Record<string, unknown>,
  existingRels: Relationship[],
): Relationship[] {
  const existing = new Set(existingRels.map(r => `${r.from}|${r.property}|${r.to}`))
  const derived: Relationship[] = []

  Object.entries(examples).forEach(([typeKey, example]) => {
    if (!example || typeof example !== 'object') return
    const ex = example as Record<string, unknown>
    const sourceType = ex.type
      ? (String(ex.type).split('/').pop() ?? typeKey)
      : typeKey

    Object.entries(ex).forEach(([attrKey, val]) => {
      if (attrKey === 'id' || attrKey === 'type' || attrKey === '@context') return
      if (!val || typeof val !== 'object') return

      const property = attrKey.includes('/')
        ? (attrKey.split('/').pop() ?? attrKey)
        : attrKey.includes('#')
          ? (attrKey.split('#').pop() ?? attrKey)
          : attrKey

      const v = val as Record<string, unknown>
      const addIfNew = (targetId: unknown, implicit: boolean) => {
        if (!targetId || typeof targetId !== 'string' || !targetId.startsWith('urn:ngsi-ld:')) return
        const parts = targetId.split(':')
        const targetType = parts[2] ?? null
        if (!targetType) return
        const key = `${sourceType}|${property}|${targetType}`
        if (existing.has(key)) return
        existing.add(key)
        derived.push({
          from: sourceType,
          property,
          to: targetType,
          implicit,
          description: implicit ? 'Derivada de ejemplos (Property con URN)' : 'Derivada de ejemplos',
        })
      }

      if (v.type === 'Relationship' && v.object) {
        const targets = Array.isArray(v.object) ? v.object : [v.object]
        targets.forEach(t => addIfNew(typeof t === 'string' ? t : (t as { id?: string })?.id, false))
        return
      }
      if (v.type === 'Property' && v.value) {
        if (typeof v.value === 'string') addIfNew(v.value, true)
        else if (Array.isArray(v.value)) v.value.forEach(x => addIfNew(x, true))
      }
    })
  })
  return derived
}

function getContextMapping(context: unknown): Record<string, unknown> | null {
  if (!context) return null
  let obj: unknown = context
  if (Array.isArray(obj)) {
    obj = (obj as unknown[]).find(item => item && typeof item === 'object' && !Array.isArray(item)) ?? {}
  }
  if (typeof obj !== 'object' || obj === null) return null
  const rec = obj as Record<string, unknown>
  if (rec['@context']) obj = rec['@context']
  if (Array.isArray(obj)) obj = (obj as unknown[]).find(item => item && typeof item === 'object') ?? {}
  return typeof obj === 'object' ? (obj as Record<string, unknown>) : null
}

export function getTypeUri(typeName: string, storedModelJson: string | null): string {
  if (!typeName || !storedModelJson) return typeName
  try {
    const m = JSON.parse(storedModelJson) as Record<string, unknown>
    const mapping = getContextMapping(m.context)
    if (!mapping || !mapping[typeName]) return typeName
    return mapping[typeName] as string
  } catch {
    return typeName
  }
}

export function getContextForPayload(storedModelJson: string | null): ContextValue {
  const fallback = 'https://uri.etsi.org/ngsi-ld/v1/ngsi-ld-core-context.jsonld'
  if (!storedModelJson) return fallback
  let m: Record<string, unknown>
  try {
    m = JSON.parse(storedModelJson) as Record<string, unknown>
  } catch {
    return fallback
  }
  if (m.contextUrl && typeof m.contextUrl === 'string') {
    const u = m.contextUrl.toLowerCase()
    const isLocal = u.includes('://localhost') || u.includes('://127.0.0.1')
    if (!isLocal) return m.contextUrl
    const backendOrigin = window.location.origin
      .replace('localhost', 'host.docker.internal')
      .replace('127.0.0.1', 'host.docker.internal')
    return `${backendOrigin}/api/context?url=${encodeURIComponent(m.contextUrl)}`
  }
  const ctx = m.context as Record<string, unknown> | undefined
  if (!ctx) return fallback
  if (ctx['@context'] != null) return ctx['@context'] as ContextValue
  return ctx as ContextValue
}

function normalizeExpandedIri(iri: string): string {
  return iri.replace(/\/$/, '')
}

function collectTermToIriPairs(leaf: Record<string, unknown>, into: [string, string][]): void {
  Object.entries(leaf).forEach(([term, def]) => {
    if (term.startsWith('@')) return
    if (typeof def === 'string') {
      if (def.startsWith('http://') || def.startsWith('https://') || def.startsWith('urn:'))
        into.push([term, def])
      return
    }
    if (def && typeof def === 'object') {
      const id = (def as Record<string, unknown>)['@id']
      if (typeof id === 'string' && (id.startsWith('http://') || id.startsWith('https://') || id.startsWith('urn:')))
        into.push([term, id])
    }
  })
}

function buildExpandedIriToPreferredTerm(contextValue: unknown): Map<string, string> {
  const pairs: [string, string][] = []
  const addBlock = (block: unknown) => {
    if (block && typeof block === 'object' && !Array.isArray(block))
      collectTermToIriPairs(block as Record<string, unknown>, pairs)
  }
  if (Array.isArray(contextValue)) {
    contextValue.forEach(item => { if (typeof item !== 'string') addBlock(item) })
  } else {
    addBlock(contextValue)
  }
  const iriToTerms = new Map<string, string[]>()
  pairs.forEach(([term, iri]) => {
    const k = normalizeExpandedIri(iri)
    if (!iriToTerms.has(k)) iriToTerms.set(k, [])
    iriToTerms.get(k)!.push(term)
  })
  const preferred = new Map<string, string>()
  iriToTerms.forEach((terms, iri) => {
    const uniq = [...new Set(terms)].sort((a, b) => a.length - b.length || a.localeCompare(b))
    preferred.set(iri, uniq[0])
  })
  return preferred
}

function resolveContextBlocksForCompaction(
  contextForPayload: ContextValue,
  storedModelJson: string | null,
): Record<string, unknown>[] {
  const out: Record<string, unknown>[] = []
  if (Array.isArray(contextForPayload)) {
    contextForPayload.forEach(item => {
      if (typeof item !== 'string' && item && typeof item === 'object') out.push(item as Record<string, unknown>)
    })
    if (out.length) return out
  } else if (contextForPayload && typeof contextForPayload === 'object') {
    return [contextForPayload as Record<string, unknown>]
  }
  if (!storedModelJson) return []
  try {
    const m = JSON.parse(storedModelJson) as Record<string, unknown>
    if (!m?.context) return []
    const c = m.context as Record<string, unknown>
    const inner = c['@context'] != null ? c['@context'] : c
    if (Array.isArray(inner)) {
      inner.forEach(item => {
        if (typeof item !== 'string' && item && typeof item === 'object') out.push(item as Record<string, unknown>)
      })
    } else if (inner && typeof inner === 'object') {
      out.push(inner as Record<string, unknown>)
    }
  } catch { /* ignore */ }
  return out
}

function expandedIriToCompactKey(iri: string, lookupIri: (full: string) => string | null): string {
  if (iri.includes('#')) return lookupIri(iri) ?? iri.split('#').pop() ?? iri
  const parts = iri.split('/').filter(Boolean)
  const last = parts.length ? parts[parts.length - 1] : iri
  return lookupIri(iri) ?? last
}

export function compactAttributeKeysForSchema(
  entity: Record<string, unknown>,
  contextForPayload: ContextValue,
  storedModelJson: string | null,
): Record<string, unknown> {
  if (!entity || typeof entity !== 'object') return entity
  const blocks = resolveContextBlocksForCompaction(contextForPayload, storedModelJson)
  const maps = blocks.map(buildExpandedIriToPreferredTerm)

  const lookupIri = (iri: string): string | null => {
    const norm = normalizeExpandedIri(iri)
    for (const m of maps) {
      if (m.has(norm)) return m.get(norm)!
      if (m.has(iri)) return m.get(iri)!
    }
    return null
  }

  const out: Record<string, unknown> = {}
  for (const [k, v] of Object.entries(entity)) {
    if (k === 'id' || k === 'type' || k === '@context') { out[k] = v; continue }
    let shortKey = k
    if (k.startsWith('http://') || k.startsWith('https://')) {
      shortKey = expandedIriToCompactKey(k, lookupIri)
    }
    if (Object.prototype.hasOwnProperty.call(out, shortKey)) out[k] = v
    else out[shortKey] = v
  }
  return out
}

/** Nombre de tipo para schema/UI (p. ej. `Building` desde una URI expandida). */
export function resolveSchemaTypeName(typeValue: unknown): string {
  if (typeValue == null || typeValue === '') return ''
  const s = String(typeValue)
  if (s.includes('/')) return s.split('/').pop() ?? s
  if (s.includes('#')) return s.split('#').pop() ?? s
  return s
}

/** JSON del chat/Orion (claves expandidas) → formato del editor de creación. */
export function normalizeImportedEntityPayload(
  raw: Record<string, unknown>,
  storedModelJson: string | null,
): Record<string, unknown> {
  const type = resolveSchemaTypeName(raw.type)
  const ctx = getContextForPayload(storedModelJson)
  const clone = JSON.parse(JSON.stringify(raw)) as Record<string, unknown>
  if (type) clone.type = type
  const compacted = compactAttributeKeysForSchema(clone, ctx, storedModelJson)
  if (type) compacted.type = type
  if (compacted['@context'] == null) compacted['@context'] = ctx
  return compacted
}

export function parseModel(storedModelJson: string | null): ParsedModel {
  if (!storedModelJson) return { types: [], relationships: [] }
  let m: Record<string, unknown>
  try {
    m = JSON.parse(storedModelJson) as Record<string, unknown>
  } catch {
    return { types: [], relationships: [] }
  }
  const types = new Set<string>()
  let relationships: Relationship[] = []

  if (m.descriptor) {
    getTypesFromDescriptor(m.descriptor).forEach(t => types.add(t))
    relationships = getRelationshipsFromDescriptor(m.descriptor)
  }
  if (m.context) getTypesFromContext(m.context).forEach(t => types.add(t))
  if (Array.isArray(m.schemas)) getTypesFromSchemas(m.schemas).forEach(t => types.add(t))

  if (m.examples && typeof m.examples === 'object') {
    const derived = getRelationshipsFromExamples(m.examples as Record<string, unknown>, relationships)
    relationships = [...relationships, ...derived]
    derived.forEach(r => { types.add(r.from); types.add(r.to) })
  }
  return { types: Array.from(types).sort(), relationships }
}

export function getExampleForType(typeName: string, storedModelJson: string | null): Record<string, unknown> | null {
  if (!typeName || !storedModelJson) return null
  try {
    const m = JSON.parse(storedModelJson) as Record<string, unknown>
    const examples = m.examples
    if (!examples || typeof examples !== 'object') return null
    const ex = examples as Record<string, unknown>
    const lower = typeName.toLowerCase()
    if (ex[typeName] != null) return ex[typeName] as Record<string, unknown>
    for (const [k, v] of Object.entries(ex)) {
      if (k.toLowerCase() === lower) return v as Record<string, unknown>
    }
  } catch { /* ignore */ }
  return null
}

export function getSchemaForType(typeName: string, storedModelJson: string | null): unknown {
  if (!typeName || !storedModelJson) return null
  try {
    const m = JSON.parse(storedModelJson) as Record<string, unknown>
    const schemas = m.schemas as Record<string, unknown>[] | undefined
    if (!Array.isArray(schemas)) return null
    for (const s of schemas) {
      const name =
        normalizeSchemaTitle(s.title) ??
        (typeof s.$id === 'string' ? s.$id.split('/').pop()!.replace(/\.json$/, '') : null)
      if (name === typeName) return s
    }
  } catch { /* ignore */ }
  return null
}

export function buildCreateBasePayload(
  type: string,
  storedModelJson: string | null,
): { payload: Record<string, unknown>; fromExample: boolean } {
  const ctx = getContextForPayload(storedModelJson)
  const example = getExampleForType(type, storedModelJson)
  if (example && typeof example === 'object') {
    const base: Record<string, unknown> = { ...example }
    base.type = type
    if (!base.id) base.id = `urn:ngsi-ld:${type}:001`
    base['@context'] = ctx
    return { payload: base, fromExample: true }
  }
  return {
    payload: { id: `urn:ngsi-ld:${type}:001`, type, '@context': ctx },
    fromExample: false,
  }
}
