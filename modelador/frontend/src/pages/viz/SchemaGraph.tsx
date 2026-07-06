import * as d3 from 'd3'
import { forwardRef, useEffect, useImperativeHandle, useRef } from 'react'
import { zoomFit, appendGraphNodeLabel, graphNodeCollisionRadius, splitGraphNodeLabel, type GraphLabelPlacement } from '../../lib/graph-utils'
import type { SchemaGraphLink, SchemaGraphNode } from '../../types/graph'

export type GraphHandle = {
  zoomIn: () => void
  zoomOut: () => void
  fit: () => void
  /** Encuadra todos los nodos visibles (ignora foco de entidad). */
  fitVisible: () => void
  highlightNode: (nodeId: string) => void
  clearHighlight: () => void
  zoomToFocusedNode: () => void
}

type SimNode = SchemaGraphNode & d3.SimulationNodeDatum
type SimLink = d3.SimulationLinkDatum<SimNode> & { property?: string; implicit?: boolean }

type Props = {
  nodes: SchemaGraphNode[]
  links: SchemaGraphLink[]
  colorScale: d3.ScaleOrdinal<string, string, never>
  labelPlacement?: GraphLabelPlacement
  onNodeClick: (typeId: string | null) => void
}

export const SchemaGraph = forwardRef<GraphHandle, Props>(function SchemaGraph(
  { nodes, links, colorScale, labelPlacement = 'below', onNodeClick },
  ref,
) {
  const svgRef = useRef<SVGSVGElement>(null)
  const containerRef = useRef<HTMLDivElement>(null)
  const zoomRef = useRef<d3.ZoomBehavior<SVGSVGElement, unknown> | null>(null)
  const svgD3Ref = useRef<d3.Selection<SVGSVGElement, unknown, null, undefined> | null>(null)
  const gRef = useRef<d3.Selection<SVGGElement, unknown, null, undefined> | null>(null)
  const simRef = useRef<d3.Simulation<SimNode, SimLink> | null>(null)
  // Stable ref for the click callback — avoids restarting the simulation on every parent render
  const onNodeClickRef = useRef(onNodeClick)
  useEffect(() => { onNodeClickRef.current = onNodeClick })

  useImperativeHandle(ref, () => ({
    zoomIn: () => {
      if (svgD3Ref.current && zoomRef.current)
        svgD3Ref.current.transition().duration(300).call(zoomRef.current.scaleBy, 1.4)
    },
    zoomOut: () => {
      if (svgD3Ref.current && zoomRef.current)
        svgD3Ref.current.transition().duration(300).call(zoomRef.current.scaleBy, 1 / 1.4)
    },
    fit: () => {
      if (svgD3Ref.current && gRef.current && zoomRef.current)
        zoomFit(svgD3Ref.current, gRef.current, zoomRef.current)
    },
    fitVisible: () => {
      if (svgD3Ref.current && gRef.current && zoomRef.current)
        zoomFit(svgD3Ref.current, gRef.current, zoomRef.current)
    },
    highlightNode: () => {},
    clearHighlight: () => {},
    zoomToFocusedNode: () => {},
  }))

  // Main D3 effect — reruns only when data or color scale changes
  useEffect(() => {
    if (!svgRef.current || !containerRef.current || !nodes.length) return
    simRef.current?.stop()

    const container = containerRef.current
    const w = container.clientWidth || 900
    const h = container.clientHeight || 600

    const nodesCopy: SimNode[] = nodes.map((n) => ({ ...n }))
    const linksCopy: SimLink[] = links.map((l) => ({
      source: typeof l.source === 'string' ? l.source : (l.source as SchemaGraphNode).id,
      target: typeof l.target === 'string' ? l.target : (l.target as SchemaGraphNode).id,
      property: l.property,
      implicit: l.implicit,
    }))

    const svgD3 = d3.select(svgRef.current).attr('viewBox', [0, 0, w, h] as unknown as string)
    svgD3.selectAll('*').remove()
    svgD3Ref.current = svgD3

    const defs = svgD3.append('defs')
    defs
      .append('marker')
      .attr('id', 'arrowSchema')
      .attr('viewBox', '0 -5 10 10')
      .attr('refX', 10)
      .attr('refY', 0)
      .attr('markerWidth', 7)
      .attr('markerHeight', 7)
      .attr('orient', 'auto')
      .append('path')
      .attr('d', 'M0,-5L10,0L0,5')
      .attr('fill', 'var(--muted)')
    defs
      .append('marker')
      .attr('id', 'arrowSchemaImpl')
      .attr('viewBox', '0 -5 10 10')
      .attr('refX', 10)
      .attr('refY', 0)
      .attr('markerWidth', 7)
      .attr('markerHeight', 7)
      .attr('orient', 'auto')
      .append('path')
      .attr('d', 'M0,-5L10,0L0,5')
      .attr('fill', 'var(--implicit-line)')

    const g = svgD3.append('g')
    gRef.current = g

    const zoom = d3.zoom<SVGSVGElement, unknown>().scaleExtent([0.1, 4]).on('zoom', (e) => g.attr('transform', e.transform))
    svgD3.call(zoom)
    zoomRef.current = zoom

    // Degree calculation for node radius
    const totalDeg: Record<string, number> = {}
    nodesCopy.forEach((n) => { totalDeg[n.id] = 0 })
    linksCopy.forEach((l) => {
      const s = typeof l.source === 'string' ? l.source : (l.source as SimNode).id
      const t = typeof l.target === 'string' ? l.target : (l.target as SimNode).id
      totalDeg[s] = (totalDeg[s] || 0) + 1
      totalDeg[t] = (totalDeg[t] || 0) + 1
    })
    const maxDeg = Math.max(1, ...Object.values(totalDeg))
    const nodeRadius = (d: SimNode) => 20 + 18 * ((totalDeg[d.id] || 0) / maxDeg)

    // Seed positions in a circle
    const cx = w / 2
    const cy = h / 2
    const seedR = Math.max(120, Math.min(w, h) * 0.28)
    const sorted = [...nodesCopy].sort((a, b) => (totalDeg[b.id] - totalDeg[a.id]) || a.id.localeCompare(b.id))
    sorted.forEach((n, i) => {
      const angle = (2 * Math.PI * i) / Math.max(1, sorted.length)
      n.x = cx + Math.cos(angle) * seedR
      n.y = cy + Math.sin(angle) * seedR
    })

    const sim = d3
      .forceSimulation<SimNode>(nodesCopy)
      .force(
        'link',
        d3
          .forceLink<SimNode, SimLink>(linksCopy)
          .id((d) => d.id)
          .distance((d) => (d.implicit ? 170 : 135))
          .strength(0.22),
      )
      .force('charge', d3.forceManyBody().strength(-420))
      .force('center', d3.forceCenter(w / 2, h / 2))
      .force('collide', d3.forceCollide<SimNode>().radius((d) => {
        const lines = splitGraphNodeLabel(d.id).length
        return graphNodeCollisionRadius(nodeRadius(d), lines, labelPlacement)
      }))
    simRef.current = sim

    const schemaLink = g
      .append('g')
      .selectAll<SVGLineElement, SimLink>('line')
      .data(linksCopy)
      .join('line')
      .attr('class', (d) => (d.implicit ? 'link schema-link-implicit' : 'link'))
      .attr('marker-end', (d) => (d.implicit ? 'url(#arrowSchemaImpl)' : 'url(#arrowSchema)'))

    const schemaLinkLabel = g
      .append('g')
      .selectAll<SVGTextElement, SimLink>('text')
      .data(linksCopy)
      .join('text')
      .attr('class', 'link-label')
      .text((d) => d.property || '')

    function highlight(hoveredId: string) {
      const connected = new Set([hoveredId])
      schemaLink.each((d) => {
        const s = (d.source as SimNode).id ?? d.source
        const t = (d.target as SimNode).id ?? d.target
        if (s === hoveredId) connected.add(t as string)
        if (t === hoveredId) connected.add(s as string)
      })
      schemaNode.style('opacity', (d) => (connected.has(d.id) ? 1 : 0.08))
      schemaLink.style('opacity', (d) => {
        const s = (d.source as SimNode).id ?? d.source
        const t = (d.target as SimNode).id ?? d.target
        return s === hoveredId || t === hoveredId ? 0.9 : 0.04
      })
      schemaLinkLabel.style('opacity', (d) => {
        const s = (d.source as SimNode).id ?? d.source
        const t = (d.target as SimNode).id ?? d.target
        return s === hoveredId || t === hoveredId ? 1 : 0
      })
    }

    function clearHighlight() {
      schemaNode.style('opacity', null)
      schemaLink.style('opacity', null)
      schemaLinkLabel.style('opacity', null)
    }

    let dragged = false
    const schemaNode = g
      .append('g')
      .selectAll<SVGGElement, SimNode>('g')
      .data(nodesCopy)
      .join('g')
      .attr('class', 'node')
      .call(
        d3
          .drag<SVGGElement, SimNode>()
          .on('start', (e, d) => {
            dragged = false
            if (!e.active) sim.alphaTarget(0.3).restart()
            d.fx = d.x
            d.fy = d.y
          })
          .on('drag', (e, d) => {
            dragged = true
            d.fx = e.x
            d.fy = e.y
          })
          .on('end', (e, d) => {
            if (!e.active) sim.alphaTarget(0)
            d.fx = null
            d.fy = null
          }),
      )
      .on('mouseenter', (_e, d) => highlight(d.id))
      .on('mouseleave', clearHighlight)
      .on('click', (_e, d) => {
        if (dragged) return
        _e.stopPropagation()
        onNodeClickRef.current(d.id)
      })

    svgD3.on('click', () => onNodeClickRef.current(null))

    schemaNode.append('title').text((d) => d.id)
    schemaNode
      .append('circle')
      .attr('r', (d) => nodeRadius(d))
      .style('fill', (d) => colorScale(d.id))
      .style('stroke', (d) => (d3.color(colorScale(d.id))?.darker(0.8)?.toString() ?? colorScale(d.id)))
    appendGraphNodeLabel(schemaNode, (d) => d.id, nodeRadius, { placement: labelPlacement })

    sim.on('tick', () => {
      schemaLink.each(function (d) {
        const src = d.source as SimNode
        const tgt = d.target as SimNode
        const dx = (tgt.x ?? 0) - (src.x ?? 0)
        const dy = (tgt.y ?? 0) - (src.y ?? 0)
        const dist = Math.hypot(dx, dy) || 1
        const rs = nodeRadius(src)
        const rt = nodeRadius(tgt) + 3
        d3.select(this)
          .attr('x1', (src.x ?? 0) + (dx / dist) * rs)
          .attr('y1', (src.y ?? 0) + (dy / dist) * rs)
          .attr('x2', (tgt.x ?? 0) - (dx / dist) * rt)
          .attr('y2', (tgt.y ?? 0) - (dy / dist) * rt)
      })
      schemaLinkLabel
        .attr('x', (d) => ((d.source as SimNode).x! + (d.target as SimNode).x!) / 2)
        .attr('y', (d) => ((d.source as SimNode).y! + (d.target as SimNode).y!) / 2 - 6)
      schemaNode.attr('transform', (d) => `translate(${d.x ?? 0},${d.y ?? 0})`)
    })

    return () => {
      sim.stop()
    }
    // onNodeClick intentionally excluded — handled via ref to avoid restarting the sim
  }, [nodes, links, colorScale, labelPlacement])

  return (
    <div ref={containerRef} style={{ width: '100%', height: '100%', position: 'relative' }}>
      <svg ref={svgRef} style={{ display: 'block', width: '100%', height: '100%' }} />
    </div>
  )
})
