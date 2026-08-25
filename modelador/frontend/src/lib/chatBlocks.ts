import i18n from '../lib/i18n'
import i18n from '../lib/i18n'
export type ChatEntityRow = {
  id: string
  type?: string
  name?: string
}

export type ChatGraphNode = {
  id: string
  label?: string
}

export type ChatGraphEdge = {
  source: string
  target: string
  label?: string
}

export type ChatBlock =
  | { kind: 'entity-list'; entities: ChatEntityRow[] }
  | { kind: 'json'; title?: string; value: unknown }
  | { kind: 'graph'; nodes: ChatGraphNode[]; edges: ChatGraphEdge[] }

function entityNameFromRecord(row: Record<string, unknown>): string | undefined {
  const name = row.name
  if (typeof name === 'string' && name.trim()) return name.trim()
  if (name && typeof name === 'object' && 'value' in name) {
    const v = (name as { value?: unknown }).value
    if (typeof v === 'string' && v.trim()) return v.trim()
  }
  return undefined
}

export function normalizeEntityRow(item: unknown): ChatEntityRow | null {
  if (!item || typeof item !== 'object') return null
  const row = item as Record<string, unknown>
  const rawId = row.id ?? row['@id']
  if (rawId == null || String(rawId).trim() === '') return null
  const id = String(rawId).trim()
  let type: string | undefined
  if (row.type != null) {
    type = String(row.type).split('/').pop() || String(row.type)
  }
  return { id, type, name: entityNameFromRecord(row) }
}

function parseGraphBlock(raw: unknown): ChatBlock | null {
  if (!raw || typeof raw !== 'object') return null
  const g = raw as Record<string, unknown>
  const nodesRaw = g.nodes ?? g.entities
  const edgesRaw = g.edges ?? g.relationships ?? g.links
  if (!Array.isArray(nodesRaw) || !Array.isArray(edgesRaw)) return null

  const nodes: ChatGraphNode[] = []
  for (const n of nodesRaw) {
    if (!n || typeof n !== 'object') continue
    const o = n as Record<string, unknown>
    const id = String(o.id ?? o['@id'] ?? o.name ?? '').trim()
    if (!id) continue
    const label = o.label != null ? String(o.label) : entityNameFromRecord(o) ?? id.split(':').pop()
    nodes.push({ id, label })
  }

  const edges: ChatGraphEdge[] = []
  for (const e of edgesRaw) {
    if (!e || typeof e !== 'object') continue
    const o = e as Record<string, unknown>
    const source = String(o.source ?? o.from ?? o.subject ?? '').trim()
    const target = String(o.target ?? o.to ?? o.object ?? '').trim()
    if (!source || !target) continue
    const label = o.label != null ? String(o.label) : o.rel != null ? String(o.rel) : undefined
    edges.push({ source, target, label })
  }

  if (!nodes.length && !edges.length) return null
  return { kind: 'graph', nodes, edges }
}

function parseJsonBlock(value: unknown, title?: string): ChatBlock | null {
  if (value == null) return null
  if (typeof value === 'string') {
    try {
      return { kind: 'json', title, value: JSON.parse(value) as unknown }
    } catch {
      return { kind: 'json', title, value }
    }
  }
  return { kind: 'json', title, value }
}

function parseBlockEntry(entry: unknown): ChatBlock | null {
  if (!entry || typeof entry !== 'object') return null
  const b = entry as Record<string, unknown>
  const kind = String(b.kind ?? b.type ?? '')

  if (kind === 'entity-list' || kind === 'entities') {
    const arr = b.entities ?? b.items
    if (!Array.isArray(arr)) return null
    const entities = arr.map(normalizeEntityRow).filter((r): r is ChatEntityRow => r != null)
    return entities.length ? { kind: 'entity-list', entities } : null
  }
  if (kind === 'json' || kind === 'entity' || kind === 'payload') {
    return parseJsonBlock(b.value ?? b.payload ?? b.entity, b.title != null ? String(b.title) : undefined)
  }
  if (kind === 'graph') {
    return parseGraphBlock(b.graph ?? b)
  }
  return null
}

/** Interpreta el campo `data` del agente LLM / AEA en bloques de UI. */
export function parseChatBlocks(data: Record<string, unknown> | undefined | null): ChatBlock[] {
  if (!data || typeof data !== 'object') return []

  const blocks: ChatBlock[] = []

  if (Array.isArray(data.blocks)) {
    for (const entry of data.blocks) {
      const block = parseBlockEntry(entry)
      if (block) blocks.push(block)
    }
    if (blocks.length) return blocks
  }

  const entityArrays = [data.entities, data.entity_list, data.items].filter(Array.isArray)
  for (const arr of entityArrays) {
    const entities = (arr as unknown[]).map(normalizeEntityRow).filter((r): r is ChatEntityRow => r != null)
    if (entities.length) {
      blocks.push({ kind: 'entity-list', entities })
      break
    }
  }

  const jsonCandidates: Array<[unknown, string | undefined]> = [
    [data.entity, i18n.t('agent.blocks.entityTitle')],
    [data.payload, i18n.t('agent.blocks.payloadTitle')],
    [data.ngsi_ld, 'NGSI-LD'],
  ]
  for (const [value, title] of jsonCandidates) {
    const block = parseJsonBlock(value, title)
    if (block) blocks.push(block)
  }

  const graphBlock = parseGraphBlock(data.graph ?? (data.nodes && data.edges ? data : null))
  if (graphBlock) blocks.push(graphBlock)

  if (Array.isArray(data.relationships) && !blocks.some((b) => b.kind === 'graph')) {
    const edges: ChatGraphEdge[] = []
    const nodeIds = new Set<string>()
    for (const rel of data.relationships) {
      if (!rel || typeof rel !== 'object') continue
      const o = rel as Record<string, unknown>
      const source = String(o.source ?? o.from ?? '').trim()
      const target = String(o.target ?? o.to ?? '').trim()
      if (!source || !target) continue
      nodeIds.add(source)
      nodeIds.add(target)
      edges.push({
        source,
        target,
        label: o.label != null ? String(o.label) : o.name != null ? String(o.name) : undefined,
      })
    }
    if (edges.length) {
      blocks.push({
        kind: 'graph',
        nodes: [...nodeIds].map((id) => ({ id, label: id.split(':').pop() || id })),
        edges,
      })
    }
  }

  return blocks
}
