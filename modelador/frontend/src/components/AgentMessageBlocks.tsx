import { useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  dispatchAgentApplyEntity,
  dispatchAgentOpenEntity,
  dispatchAgentOpenVizEntity,
} from '../lib/agentEvents'
import { normalizeImportedEntityPayload } from '../lib/model-parser'
import { setVizFocusEntityId } from '../lib/vizNavigation'
import type { ChatBlock, ChatEntityRow, ChatGraphEdge, ChatGraphNode } from '../lib/chatBlocks'
import { AgentGraphBlock } from './AgentGraphBlock'

type Props = {
  blocks: ChatBlock[]
}

function jsonPreview(value: unknown): string {
  try {
    return JSON.stringify(value, null, 2)
  } catch {
    return String(value)
  }
}

function entityPayload(value: unknown): Record<string, unknown> | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null
  return value as Record<string, unknown>
}

function entityIdFromPayload(payload: Record<string, unknown>): string | null {
  const id = payload.id
  if (typeof id === 'string' && id.startsWith('urn:ngsi-ld:')) return id
  return null
}

function pickGraphFocusNode(nodes: ChatGraphNode[], edges: ChatGraphEdge[]): string | null {
  if (!nodes.length) return null
  if (nodes.length === 1) return nodes[0].id
  const degree = new Map<string, number>()
  edges.forEach((e) => {
    degree.set(e.source, (degree.get(e.source) ?? 0) + 1)
    degree.set(e.target, (degree.get(e.target) ?? 0) + 1)
  })
  let best = nodes[0].id
  let bestScore = -1
  for (const n of nodes) {
    const score = degree.get(n.id) ?? 0
    if (score > bestScore) {
      bestScore = score
      best = n.id
    }
  }
  return best.startsWith('urn:ngsi-ld:') ? best : null
}

function useGoOrionViz() {
  const navigate = useNavigate()
  return (entityId: string) => {
    if (!entityId.startsWith('urn:ngsi-ld:')) return
    setVizFocusEntityId(entityId)
    dispatchAgentOpenVizEntity({ entityId })
    navigate('/visualizacion')
  }
}

export function AgentMessageBlocks({ blocks }: Props) {
  const navigate = useNavigate()
  const goOrionViz = useGoOrionViz()

  if (!blocks.length) return null

  return (
    <div className="agent-message-blocks">
      {blocks.map((block, index) => (
        <AgentBlock
          key={`${block.kind}-${index}`}
          block={block}
          onGoEntities={() => navigate('/entidades')}
          onGoOrionViz={goOrionViz}
        />
      ))}
    </div>
  )
}

function AgentBlock({
  block,
  onGoEntities,
  onGoOrionViz,
}: {
  block: ChatBlock
  onGoEntities: () => void
  onGoOrionViz: (entityId: string) => void
}) {
  if (block.kind === 'entity-list') {
    return <EntityListBlock entities={block.entities} onGoEntities={onGoEntities} onGoOrionViz={onGoOrionViz} />
  }
  if (block.kind === 'json') {
    return <JsonBlock title={block.title} value={block.value} onGoEntities={onGoEntities} onGoOrionViz={onGoOrionViz} />
  }
  if (block.kind === 'graph') {
    return <GraphBlock nodes={block.nodes} edges={block.edges} onGoOrionViz={onGoOrionViz} />
  }
  return null
}

function EntityListBlock({
  entities,
  onGoEntities,
  onGoOrionViz,
}: {
  entities: ChatEntityRow[]
  onGoEntities: () => void
  onGoOrionViz: (entityId: string) => void
}) {
  return (
    <div className="agent-block agent-block--entities">
      <div className="agent-block-title">Entidades ({entities.length})</div>
      <div className="agent-block-table-wrap">
        <table className="agent-block-table">
          <thead>
            <tr>
              <th>Tipo</th>
              <th>Identificador</th>
              <th aria-label="Acciones" />
            </tr>
          </thead>
          <tbody>
            {entities.map((row) => (
              <tr key={row.id}>
                <td>{row.type ?? '—'}</td>
                <td className="agent-block-mono" title={row.id}>
                  {row.name ?? row.id.split(':').pop() ?? row.id}
                </td>
                <td className="agent-block-actions-cell">
                  <button
                    type="button"
                    className="agent-block-link"
                    onClick={() => {
                      onGoEntities()
                      dispatchAgentOpenEntity({ entityId: row.id })
                    }}
                  >
                    Abrir
                  </button>
                  {row.id.startsWith('urn:ngsi-ld:') && (
                    <button
                      type="button"
                      className="agent-block-link"
                      onClick={() => onGoOrionViz(row.id)}
                    >
                      Ver relaciones
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function JsonBlock({
  title,
  value,
  onGoEntities,
  onGoOrionViz,
}: {
  title?: string
  value: unknown
  onGoEntities: () => void
  onGoOrionViz: (entityId: string) => void
}) {
  const [copied, setCopied] = useState(false)
  const text = useMemo(() => jsonPreview(value), [value])
  const payload = entityPayload(value)
  const entityId = payload ? entityIdFromPayload(payload) : null

  async function handleCopy() {
    try {
      await navigator.clipboard.writeText(text)
      setCopied(true)
      window.setTimeout(() => setCopied(false), 2000)
    } catch {
      /* ignore */
    }
  }

  function handleApply() {
    if (!payload) return
    const modelJson = localStorage.getItem('ngsi_model')
    const normalized = normalizeImportedEntityPayload(payload, modelJson)
    onGoEntities()
    dispatchAgentApplyEntity({ payload: normalized, mode: 'create' })
  }

  return (
    <div className="agent-block agent-block--json">
      {title && <div className="agent-block-title">{title}</div>}
      <pre className="agent-block-json">{text}</pre>
      <div className="agent-block-actions">
        <button type="button" className="secondary agent-block-btn" onClick={handleCopy}>
          {copied ? 'Copiado' : 'Copiar JSON'}
        </button>
        {payload && (
          <button type="button" className="agent-block-btn" onClick={handleApply}>
            Abrir en editor
          </button>
        )}
        {entityId && (
          <button type="button" className="secondary agent-block-btn" onClick={() => onGoOrionViz(entityId)}>
            Ver relaciones
          </button>
        )}
      </div>
    </div>
  )
}

function GraphBlock({
  nodes,
  edges,
  onGoOrionViz,
}: {
  nodes: ChatGraphNode[]
  edges: ChatGraphEdge[]
  onGoOrionViz: (entityId: string) => void
}) {
  const focusId = useMemo(() => pickGraphFocusNode(nodes, edges), [nodes, edges])

  return (
    <div className="agent-block agent-block--graph">
      <AgentGraphBlock nodes={nodes} edges={edges} />
      {focusId && (
        <div className="agent-block-actions">
          <button type="button" className="agent-block-btn" onClick={() => onGoOrionViz(focusId)}>
            Ver en visualización
          </button>
        </div>
      )}
    </div>
  )
}
