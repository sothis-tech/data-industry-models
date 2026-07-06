import * as d3 from 'd3'
import { forwardRef, useEffect, useImperativeHandle, useLayoutEffect, useRef } from 'react'
import { resolveTypeColor, zoomFit, zoomToExtent, appendGraphNodeLabel, graphNodeCollisionRadius, splitGraphNodeLabel, type GraphLabelPlacement } from '../../lib/graph-utils'
import type { OrionGraphLink, OrionGraphNode } from '../../types/graph'
import type { GraphHandle } from './SchemaGraph'

type SimNode = OrionGraphNode & d3.SimulationNodeDatum
type SimLink = d3.SimulationLinkDatum<SimNode> & { property?: string; implicit?: boolean }

type Props = {
  nodes: OrionGraphNode[]
  links: OrionGraphLink[]
  visibleNodeIds: Set<string>
  colorScale: d3.ScaleOrdinal<string, string, never>
  labelPlacement?: GraphLabelPlacement
  focusedNodeId?: string | null
  searchActive?: boolean
  onNodeClick: (node: OrionGraphNode | null) => void
}

export const OrionGraph = forwardRef<GraphHandle, Props>(function OrionGraph(
  { nodes, links, visibleNodeIds, colorScale, labelPlacement = 'below', focusedNodeId, searchActive = false, onNodeClick },
  ref,
) {
  const svgRef = useRef<SVGSVGElement>(null)
  const containerRef = useRef<HTMLDivElement>(null)
  const zoomRef = useRef<d3.ZoomBehavior<SVGSVGElement, unknown> | null>(null)
  const svgD3Ref = useRef<d3.Selection<SVGSVGElement, unknown, null, undefined> | null>(null)
  const gRef = useRef<d3.Selection<SVGGElement, unknown, null, undefined> | null>(null)
  const simRef = useRef<d3.Simulation<SimNode, SimLink> | null>(null)
  const nodeSelRef = useRef<d3.Selection<SVGGElement, SimNode, SVGGElement, unknown> | null>(null)
  const linkSelRef = useRef<d3.Selection<SVGLineElement, SimLink, SVGGElement, unknown> | null>(null)
  const labelSelRef = useRef<d3.Selection<SVGTextElement, SimLink, SVGGElement, unknown> | null>(null)

  const onNodeClickRef = useRef(onNodeClick)
  useEffect(() => { onNodeClickRef.current = onNodeClick })

  const highlightApiRef = useRef<{
    highlight: (nodeId: string) => void
    clear: () => void
  } | null>(null)
  const focusedNodeIdRef = useRef<string | null>(null)

  useLayoutEffect(() => {
    focusedNodeIdRef.current = focusedNodeId ?? null
  }, [focusedNodeId])

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
      if (searchActiveRef.current) {
        zoomFitToVisibleIds()
        return
      }
      if (svgD3Ref.current && gRef.current && zoomRef.current)
        zoomFit(svgD3Ref.current, gRef.current, zoomRef.current)
    },
    fitVisible: () => {
      zoomFitToVisibleIds()
    },
    highlightNode: (nodeId) => highlightApiRef.current?.highlight(nodeId),
    clearHighlight: () => highlightApiRef.current?.clear(),
    zoomToFocusedNode: () => {},
  }))

  const visibleNodeIdsRef = useRef(visibleNodeIds)
  const searchActiveRef = useRef(searchActive)
  const prevSearchActiveRef = useRef(searchActive)
  const prevFocusedIdRef = useRef<string | null>(null)

  useEffect(() => {
    visibleNodeIdsRef.current = visibleNodeIds
  }, [visibleNodeIds])

  useEffect(() => {
    searchActiveRef.current = searchActive
  }, [searchActive])

  function applyVisibility(ids: Set<string>) {
    const nodeSel = nodeSelRef.current
    const linkSel = linkSelRef.current
    const labelSel = labelSelRef.current
    if (!nodeSel || !linkSel || !labelSel) return

    const isVisible = (id: string) => ids.has(id)
    nodeSel.classed('orion-graph-hidden', (d) => !isVisible(d.id))
    linkSel.classed('orion-graph-hidden', (d) => {
      const s = (d.source as SimNode).id ?? (d.source as string)
      const t = (d.target as SimNode).id ?? (d.target as string)
      return !isVisible(s as string) || !isVisible(t as string)
    })
    labelSel.classed('orion-graph-hidden', (d) => {
      const s = (d.source as SimNode).id ?? (d.source as string)
      const t = (d.target as SimNode).id ?? (d.target as string)
      return !isVisible(s as string) || !isVisible(t as string)
    })
    nodeSel.style('opacity', null)
    linkSel.style('opacity', null)
    labelSel.style('opacity', null)
  }

  function zoomFitToVisibleIds(padding = 48) {
    const nodeSel = nodeSelRef.current
    if (!nodeSel || !svgD3Ref.current || !zoomRef.current) return false

    const ids = visibleNodeIdsRef.current
    if (!ids.size) return false

    let x0 = Infinity
    let y0 = Infinity
    let x1 = -Infinity
    let y1 = -Infinity
    let count = 0
    nodeSel.each((d) => {
      if (!ids.has(d.id) || d.x == null || d.y == null) return
      const pad = 36
      count += 1
      x0 = Math.min(x0, d.x - pad)
      y0 = Math.min(y0, d.y - pad)
      x1 = Math.max(x1, d.x + pad)
      y1 = Math.max(y1, d.y + pad)
    })
    if (!count || !Number.isFinite(x0)) return false

    return zoomToExtent(svgD3Ref.current, zoomRef.current, x0, y0, x1, y1, padding, 500)
  }

  // Solo visibilidad (mostrar/ocultar nodos). Nunca resaltar aquí.
  useLayoutEffect(() => {
    applyVisibility(visibleNodeIds)
  }, [visibleNodeIds])

  // Al salir del modo búsqueda: restaurar visibilidad sin recentrar (el usuario conserva zoom/pan).
  useLayoutEffect(() => {
    const wasSearching = prevSearchActiveRef.current
    prevSearchActiveRef.current = searchActive
    if (!wasSearching || searchActive) return

    highlightApiRef.current?.clear()
    applyVisibility(visibleNodeIds)
  }, [searchActive, visibleNodeIds])

  // Modo búsqueda: quitar atenuación de foco
  useEffect(() => {
    if (!searchActive) return
    highlightApiRef.current?.clear()
    applyVisibility(visibleNodeIdsRef.current)
  }, [searchActive])

  // Resaltado solo al cambiar la entidad seleccionada (no al limpiar búsqueda)
  useEffect(() => {
    if (focusedNodeId === prevFocusedIdRef.current) return
    prevFocusedIdRef.current = focusedNodeId ?? null
    if (!focusedNodeId || searchActiveRef.current) {
      highlightApiRef.current?.clear()
      return
    }
    highlightApiRef.current?.highlight(focusedNodeId)
  }, [focusedNodeId])

  // Main D3 effect
  useEffect(() => {
    if (!svgRef.current || !containerRef.current || !nodes.length) return
    simRef.current?.stop()

    const container = containerRef.current
    const w = container.clientWidth || 900
    const h = container.clientHeight || 600

    const nodesCopy: SimNode[] = nodes.map((n) => ({ ...n }))
    const linksCopy: SimLink[] = links.map((l) => ({
      source: typeof l.source === 'string' ? l.source : (l.source as OrionGraphNode).id,
      target: typeof l.target === 'string' ? l.target : (l.target as OrionGraphNode).id,
      property: l.property,
      implicit: l.implicit,
    }))

    const svgD3 = d3.select(svgRef.current).attr('viewBox', [0, 0, w, h] as unknown as string)
    svgD3.selectAll('*').remove()
    svgD3Ref.current = svgD3

    const defs = svgD3.append('defs')
    ;['arrowOrion', 'arrowOrionImpl'].forEach((id, i) => {
      defs
        .append('marker')
        .attr('id', id)
        .attr('viewBox', '0 -5 10 10')
        .attr('refX', 28)
        .attr('refY', 0)
        .attr('markerWidth', 6)
        .attr('markerHeight', 6)
        .attr('orient', 'auto')
        .append('path')
        .attr('d', 'M0,-5L10,0L0,5')
        .attr('fill', i === 0 ? 'var(--muted)' : 'var(--border)')
    })

    const g = svgD3.append('g')
    gRef.current = g

    const zoom = d3.zoom<SVGSVGElement, unknown>().scaleExtent([0.1, 4]).on('zoom', (e) => g.attr('transform', e.transform))
    svgD3.call(zoom)
    zoomRef.current = zoom

    const degree: Record<string, number> = {}
    nodesCopy.forEach((n) => { degree[n.id] = 0 })
    linksCopy.forEach((l) => {
      const s = typeof l.source === 'string' ? l.source : (l.source as SimNode).id
      const t = typeof l.target === 'string' ? l.target : (l.target as SimNode).id
      degree[s] = (degree[s] || 0) + 1
      degree[t] = (degree[t] || 0) + 1
    })
    const maxDeg = Math.max(1, ...Object.values(degree))
    const nodeRadius = (d: SimNode) => 16 + 16 * ((degree[d.id] || 0) / maxDeg)
    const nodeTypeColor = (d: SimNode) => resolveTypeColor(d.type || '', colorScale)

    const sim = d3
      .forceSimulation<SimNode>(nodesCopy)
      .force(
        'link',
        d3
          .forceLink<SimNode, SimLink>(linksCopy)
          .id((d) => d.id)
          .distance((d) => (d.implicit ? 160 : 120)),
      )
      .force('charge', d3.forceManyBody().strength(-400))
      .force('center', d3.forceCenter(w / 2, h / 2))
      .force('collision', d3.forceCollide<SimNode>().radius((d) => {
        const label = d.label || d.id
        const lines = splitGraphNodeLabel(label).length
        return graphNodeCollisionRadius(nodeRadius(d), lines, labelPlacement)
      }))
    simRef.current = sim

    const link = g
      .append('g')
      .selectAll<SVGLineElement, SimLink>('line')
      .data(linksCopy)
      .join('line')
      .attr('class', (d) => (d.implicit ? 'orion-link orion-link-implicit' : 'orion-link'))
      .attr('marker-end', (d) => (d.implicit ? 'url(#arrowOrionImpl)' : 'url(#arrowOrion)'))
    linkSelRef.current = link

    const linkLabel = g
      .append('g')
      .selectAll<SVGTextElement, SimLink>('text')
      .data(linksCopy)
      .join('text')
      .attr('class', 'orion-link-label')
      .text((d) => d.property || '')
    labelSelRef.current = linkLabel

    function highlight(hoveredId: string) {
      const connected = new Set([hoveredId])
      link.each((d) => {
        const s = (d.source as SimNode).id ?? d.source
        const t = (d.target as SimNode).id ?? d.target
        if (s === hoveredId) connected.add(t as string)
        if (t === hoveredId) connected.add(s as string)
      })
      node.style('opacity', (d) => (connected.has(d.id) ? 1 : 0.08))
      link.style('opacity', (d) => {
        const s = (d.source as SimNode).id ?? d.source
        const t = (d.target as SimNode).id ?? d.target
        return s === hoveredId || t === hoveredId ? 0.9 : 0.04
      })
      linkLabel.style('opacity', (d) => {
        const s = (d.source as SimNode).id ?? d.source
        const t = (d.target as SimNode).id ?? d.target
        return s === hoveredId || t === hoveredId ? 1 : 0
      })
    }

    function clearHighlight() {
      node.style('opacity', null)
      link.style('opacity', null)
      linkLabel.style('opacity', null)
    }

    let dragged = false
    const node = g
      .append('g')
      .selectAll<SVGGElement, SimNode>('g')
      .data(nodesCopy)
      .join('g')
      .attr('class', 'orion-node')
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
      .on('mouseleave', () => {
        if (searchActiveRef.current) {
          clearHighlight()
          return
        }
        const focusId = focusedNodeIdRef.current
        if (focusId) highlight(focusId)
        else clearHighlight()
      })
      .on('click', (_e, d) => {
        if (dragged) return
        _e.stopPropagation()
        const original = nodes.find((n) => n.id === d.id) ?? d
        onNodeClickRef.current(original)
      })
    nodeSelRef.current = node

    const initialIds = visibleNodeIdsRef.current
    node.classed('orion-graph-hidden', (d) => initialIds.size > 0 && !initialIds.has(d.id))
    link.classed('orion-graph-hidden', (d) => {
      if (initialIds.size === 0) return false
      const s = (d.source as SimNode).id ?? (d.source as string)
      const t = (d.target as SimNode).id ?? (d.target as string)
      return !initialIds.has(s) || !initialIds.has(t)
    })
    linkLabel.classed('orion-graph-hidden', (d) => {
      if (initialIds.size === 0) return false
      const s = (d.source as SimNode).id ?? (d.source as string)
      const t = (d.target as SimNode).id ?? (d.target as string)
      return !initialIds.has(s) || !initialIds.has(t)
    })

    const initialFocusId = focusedNodeIdRef.current
    if (initialFocusId) highlight(initialFocusId)

    svgD3.on('click', () => onNodeClickRef.current(null))

    node.append('title').text((d) => `${d.id}\nTipo: ${(d.type || '').split('/').pop() || '–'}`)
    node
      .append('circle')
      .attr('r', (d) => nodeRadius(d))
      .style('fill', (d) => nodeTypeColor(d))
      .style('stroke', (d) => (d3.color(nodeTypeColor(d))?.darker(0.7)?.toString() ?? nodeTypeColor(d)))
    appendGraphNodeLabel(node, (d) => d.label || d.id, nodeRadius, { placement: labelPlacement })

    sim.on('tick', () => {
      link
        .attr('x1', (d) => (d.source as SimNode).x ?? 0)
        .attr('y1', (d) => (d.source as SimNode).y ?? 0)
        .attr('x2', (d) => (d.target as SimNode).x ?? 0)
        .attr('y2', (d) => (d.target as SimNode).y ?? 0)
      linkLabel
        .attr('x', (d) => ((d.source as SimNode).x! + (d.target as SimNode).x!) / 2)
        .attr('y', (d) => ((d.source as SimNode).y! + (d.target as SimNode).y!) / 2 - 5)
      node.attr('transform', (d) => `translate(${d.x ?? 0},${d.y ?? 0})`)
    })

    highlightApiRef.current = { highlight, clear: clearHighlight }

    return () => {
      highlightApiRef.current = null
      sim.stop()
    }
  }, [nodes, links, colorScale, labelPlacement])

  return (
    <div ref={containerRef} style={{ width: '100%', height: '100%', position: 'relative' }}>
      <svg ref={svgRef} style={{ display: 'block', width: '100%', height: '100%' }} />
    </div>
  )
})
