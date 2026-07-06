import { useMemo } from 'react'
import type { ChatGraphEdge, ChatGraphNode } from '../lib/chatBlocks'

type Props = {
  nodes: ChatGraphNode[]
  edges: ChatGraphEdge[]
}

const W = 280
const H = 160
const PAD = 28

export function AgentGraphBlock({ nodes, edges }: Props) {
  const layout = useMemo(() => {
    const ids = [...new Set([
      ...nodes.map((n) => n.id),
      ...edges.flatMap((e) => [e.source, e.target]),
    ])]
    const count = Math.max(ids.length, 1)
    const positions = new Map<string, { x: number; y: number }>()
    ids.forEach((id, i) => {
      const angle = (2 * Math.PI * i) / count - Math.PI / 2
      const cx = W / 2
      const cy = H / 2
      const r = Math.min(W, H) / 2 - PAD
      positions.set(id, {
        x: cx + r * Math.cos(angle),
        y: cy + r * Math.sin(angle),
      })
    })
    const labelById = new Map(nodes.map((n) => [n.id, n.label ?? n.id.split(':').pop() ?? n.id]))
    return { positions, labelById, ids }
  }, [nodes, edges])

  if (!layout.ids.length) return null

  return (
    <figure className="agent-block-graph" aria-label="Esquema de relaciones">
      <svg viewBox={`0 0 ${W} ${H}`} className="agent-block-graph-svg" role="img">
        {edges.map((edge, i) => {
          const from = layout.positions.get(edge.source)
          const to = layout.positions.get(edge.target)
          if (!from || !to) return null
          const mx = (from.x + to.x) / 2
          const my = (from.y + to.y) / 2
          return (
            <g key={`${edge.source}-${edge.target}-${i}`}>
              <line
                x1={from.x}
                y1={from.y}
                x2={to.x}
                y2={to.y}
                className="agent-block-graph-edge"
              />
              {edge.label && (
                <text x={mx} y={my} className="agent-block-graph-edge-label">
                  {edge.label}
                </text>
              )}
            </g>
          )
        })}
        {layout.ids.map((id) => {
          const p = layout.positions.get(id)
          if (!p) return null
          const label = layout.labelById.get(id) ?? id.split(':').pop() ?? id
          return (
            <g key={id} className="agent-block-graph-node">
              <circle cx={p.x} cy={p.y} r={14} />
              <text x={p.x} y={p.y + 22} textAnchor="middle">
                {label.length > 14 ? `${label.slice(0, 12)}…` : label}
              </text>
            </g>
          )
        })}
      </svg>
    </figure>
  )
}
