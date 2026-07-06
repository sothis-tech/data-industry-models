import * as d3 from 'd3'
import type { OrionGraphLink, OrionGraphNode } from '../types/graph'

type ZoomBounds = { x: number; y: number; width: number; height: number }

function viewBoxSize(svgNode: SVGSVGElement): { width: number; height: number } | null {
  const vb = svgNode.viewBox.baseVal
  if (vb.width > 0 && vb.height > 0) return { width: vb.width, height: vb.height }
  const w = svgNode.clientWidth
  const h = svgNode.clientHeight
  if (w > 0 && h > 0) return { width: w, height: h }
  return null
}

/** Encuadra [x0,x1]×[y0,y1] en coordenadas del viewBox / simulación (no píxeles CSS). */
export function zoomToExtent(
  svg: d3.Selection<SVGSVGElement, unknown, null, undefined>,
  zoom: d3.ZoomBehavior<SVGSVGElement, unknown>,
  x0: number,
  y0: number,
  x1: number,
  y1: number,
  padding = 48,
  durationMs = 500,
): boolean {
  const svgNode = svg.node()
  if (!svgNode) return false
  const size = viewBoxSize(svgNode)
  if (!size) return false

  const { width, height } = size
  const minSpan = 80
  const dx = Math.max(x1 - x0, minSpan)
  const dy = Math.max(y1 - y0, minSpan)
  const cx = (x0 + x1) / 2
  const cy = (y0 + y1) / 2

  const scale = Math.min(
    4,
    ((width - padding * 2) / dx) * 0.92,
    ((height - padding * 2) / dy) * 0.92,
  )

  const transform = d3.zoomIdentity
    .translate(width / 2, height / 2)
    .scale(scale)
    .translate(-cx, -cy)

  svg.transition().duration(durationMs).call(zoom.transform, transform)
  return true
}

function applyZoomToBounds(
  svg: d3.Selection<SVGSVGElement, unknown, null, undefined>,
  zoom: d3.ZoomBehavior<SVGSVGElement, unknown>,
  bounds: ZoomBounds,
  padding: number,
  durationMs: number,
): boolean {
  if (!bounds.width || !bounds.height) return false
  return zoomToExtent(
    svg,
    zoom,
    bounds.x,
    bounds.y,
    bounds.x + bounds.width,
    bounds.y + bounds.height,
    padding,
    durationMs,
  )
}

export function zoomToBounds(
  svg: d3.Selection<SVGSVGElement, unknown, null, undefined>,
  zoom: d3.ZoomBehavior<SVGSVGElement, unknown>,
  bounds: ZoomBounds,
  padding = 40,
  durationMs = 500,
): boolean {
  return applyZoomToBounds(svg, zoom, bounds, padding, durationMs)
}

export function zoomFit(
  svg: d3.Selection<SVGSVGElement, unknown, null, undefined>,
  g: d3.Selection<SVGGElement, unknown, null, undefined>,
  zoom: d3.ZoomBehavior<SVGSVGElement, unknown>,
): void {
  const node = g.node()
  if (!node) return
  const box = node.getBBox()
  zoomToBounds(svg, zoom, box, 24, 700)
}

export function createTypeColorScale(types: string[]): d3.ScaleOrdinal<string, string, never> {
  return d3.scaleOrdinal<string>(d3.schemeTableau10).domain(types)
}

/** Espacio entre el borde inferior del círculo y la primera línea del nombre. */
export const GRAPH_NODE_LABEL_GAP = 6
export const GRAPH_NODE_LABEL_LINE_HEIGHT = 13
export const GRAPH_NODE_LABEL_LINE_HEIGHT_INSIDE = 11
export const GRAPH_NODE_LABEL_MAX_CHARS = 28

export type GraphLabelPlacement = 'below' | 'inside'
export const GRAPH_LABEL_PLACEMENT_KEY = 'inn-viz-graph-label-placement'

export function loadGraphLabelPlacement(): GraphLabelPlacement {
  try {
    const stored = localStorage.getItem(GRAPH_LABEL_PLACEMENT_KEY)
    if (stored === 'inside' || stored === 'below') return stored
  } catch {
    /* localStorage no disponible */
  }
  return 'below'
}

export function saveGraphLabelPlacement(placement: GraphLabelPlacement): void {
  try {
    localStorage.setItem(GRAPH_LABEL_PLACEMENT_KEY, placement)
  } catch {
    /* localStorage no disponible */
  }
}

/** Parte nombres largos en varias líneas, sin truncar con "…". */
export function splitGraphNodeLabel(text: string, maxChars = GRAPH_NODE_LABEL_MAX_CHARS): string[] {
  const trimmed = text.trim()
  if (!trimmed) return ['']
  if (trimmed.length <= maxChars) return [trimmed]

  const lines: string[] = []
  let rest = trimmed

  while (rest.length > 0) {
    if (rest.length <= maxChars) {
      lines.push(rest)
      break
    }

    let cut = maxChars
    let bestBreak = -1
    for (const sep of ['-', '_', ':', '.', ' ']) {
      const idx = rest.lastIndexOf(sep, maxChars)
      if (idx > maxChars * 0.3 && idx > bestBreak) bestBreak = idx
    }
    if (bestBreak > 0) {
      cut = rest[bestBreak] === ' ' ? bestBreak + 1 : bestBreak + 1
    }

    lines.push(rest.slice(0, cut).trimEnd())
    rest = rest.slice(cut).trimStart()
  }

  return lines
}

export function graphNodeCollisionRadius(
  nodeRadius: number,
  labelLineCount: number,
  placement: GraphLabelPlacement = 'below',
): number {
  if (placement === 'inside') {
    const labelHeight = Math.max(1, labelLineCount) * GRAPH_NODE_LABEL_LINE_HEIGHT_INSIDE
    return nodeRadius + labelHeight + 8
  }
  const labelHeight = Math.max(1, labelLineCount) * GRAPH_NODE_LABEL_LINE_HEIGHT
  return nodeRadius + GRAPH_NODE_LABEL_GAP + labelHeight + 6
}

export type GraphNodeLabelOptions = {
  placement?: GraphLabelPlacement
}

/** Texto claro u oscuro según luminancia del fondo (p. ej. color del nodo). */
export function contrastTextColor(
  backgroundColor: string,
  light = '#ffffff',
  dark = '#1f2328',
): string {
  const parsed = d3.color(backgroundColor)
  if (!parsed) return dark

  const rgb = parsed.rgb()

  const toLinear = (c: number) => {
    const v = c / 255
    return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4
  }

  const luminance =
    0.2126 * toLinear(rgb.r) + 0.7152 * toLinear(rgb.g) + 0.0722 * toLinear(rgb.b)

  return luminance > 0.45 ? dark : light
}

export function appendGraphNodeLabel<G extends d3.SimulationNodeDatum>(
  node: d3.Selection<SVGGElement, G, SVGGElement, unknown>,
  getLabel: (d: G) => string,
  nodeRadius: (d: G) => number,
  options: GraphNodeLabelOptions = {},
): void {
  const placement = options.placement ?? 'below'

  node.each(function (d) {
    const group = d3.select(this)
    const r = nodeRadius(d)
    const lines = splitGraphNodeLabel(getLabel(d), GRAPH_NODE_LABEL_MAX_CHARS)

    const text = group
      .append('text')
      .attr('class', `graph-node-label${placement === 'inside' ? ' graph-node-label--inside' : ''}`)
      .attr('text-anchor', 'middle')

    if (placement === 'inside') {
      const lineCount = lines.length
      const startY = lineCount === 1 ? 4 : 4 - ((lineCount - 1) * GRAPH_NODE_LABEL_LINE_HEIGHT_INSIDE) / 2
      text.attr('y', startY)
    } else {
      text.attr('y', r + GRAPH_NODE_LABEL_GAP + GRAPH_NODE_LABEL_LINE_HEIGHT * 0.78)
    }

    const lineStep = placement === 'inside' ? GRAPH_NODE_LABEL_LINE_HEIGHT_INSIDE : GRAPH_NODE_LABEL_LINE_HEIGHT
    lines.forEach((line, index) => {
      text
        .append('tspan')
        .attr('x', 0)
        .attr('dy', index === 0 ? 0 : lineStep)
        .text(line)
    })
  })
}

export function resolveTypeColor(rawType: string, scale: d3.ScaleOrdinal<string, string, never>): string {
  return scale((rawType || '').split('/').pop() || rawType || '')
}

export function typeKeyFromFullType(rawType: string): string {
  return (rawType || '').split('/').pop() || ''
}

/** Texto del buscador al enfocar una entidad (ID corto del URN → coincide siempre con orionNodeMatchesSearch). */
export function orionEntitySearchLabel(node: OrionGraphNode): string {
  const tail = node.id.split(':').pop()
  return tail || node.id
}

export function orionNodeMatchesSearch(node: OrionGraphNode, query: string): boolean {
  const q = query.trim().toLowerCase()
  if (!q) return true
  const id = node.id.toLowerCase()
  const label = (node.label || '').toLowerCase()
  const typeKey = typeKeyFromFullType(node.type || '').toLowerCase()
  return id.includes(q) || label.includes(q) || typeKey.includes(q)
}

export function filterOrionByTypeKeys(
  allNodes: OrionGraphNode[],
  allLinks: OrionGraphLink[],
  activeTypeKeys: string[],
  allTypeKeys: string[],
): { nodes: OrionGraphNode[]; links: OrionGraphLink[] } {
  const activeSet = new Set(activeTypeKeys)
  const allTypesActive =
    allTypeKeys.length > 0 && allTypeKeys.every((k) => activeSet.has(k))
  const showUnknown = allTypesActive

  const visibleIds = new Set(
    allNodes
      .filter((n) => {
        const k = typeKeyFromFullType(n.type || '')
        return k ? activeSet.has(k) : showUnknown
      })
      .map((n) => n.id),
  )

  const filteredNodes = allNodes.filter((n) => visibleIds.has(n.id))
  const filteredLinks = allLinks.filter((l) => {
    const s = (l.source as OrionGraphNode).id ?? l.source
    const t = (l.target as OrionGraphNode).id ?? l.target
    return visibleIds.has(s as string) && visibleIds.has(t as string)
  })

  return { nodes: filteredNodes, links: filteredLinks }
}

/** Nodo focal y vecinos directos visibles según el filtro de tipos. */
export function computeOrionFocusVisibleNodeIds(
  entityId: string,
  allNodes: OrionGraphNode[],
  allLinks: OrionGraphLink[],
  activeTypeKeys: string[],
  allTypeKeys: string[],
): Set<string> {
  const { nodes: typeVisibleNodes } = filterOrionByTypeKeys(
    allNodes,
    allLinks,
    activeTypeKeys,
    allTypeKeys,
  )
  const typeVisible = new Set(typeVisibleNodes.map((n) => n.id))
  const ids = new Set<string>()

  if (typeVisible.has(entityId)) ids.add(entityId)
  else if (allNodes.some((n) => n.id === entityId)) ids.add(entityId)

  for (const l of allLinks) {
    const s = (l.source as OrionGraphNode).id ?? (l.source as string)
    const t = (l.target as OrionGraphNode).id ?? (l.target as string)
    if (s === entityId && typeVisible.has(t as string)) ids.add(t as string)
    if (t === entityId && typeVisible.has(s as string)) ids.add(s as string)
  }

  return ids
}

/**
 * Visibilidad del grafo Orion (prioridad):
 * 1. Texto de búsqueda activo → solo coincidencias.
 * 2. Sin búsqueda → filtro por tipos (checkboxes).
 *
 * El foco de entidad (highlight/zoom) no reduce nodos visibles; ver VisualizationPage.
 */
export function computeOrionVisibleNodeIds(
  allNodes: OrionGraphNode[],
  allLinks: OrionGraphLink[],
  activeTypeKeys: string[],
  allTypeKeys: string[],
  searchDraft: string,
): Set<string> {
  const q = searchDraft.trim()
  if (q) {
    return new Set(allNodes.filter((n) => orionNodeMatchesSearch(n, q)).map((n) => n.id))
  }

  const { nodes } = filterOrionByTypeKeys(allNodes, allLinks, activeTypeKeys, allTypeKeys)
  return new Set(nodes.map((n) => n.id))
}

const ORION_TYPE_FILTER_KEY = 'ngsi_orion_type_filter_keys'

export function loadSavedTypeFilter(allKeys: string[]): string[] {
  try {
    const saved = JSON.parse(localStorage.getItem(ORION_TYPE_FILTER_KEY) ?? 'null') as string[] | null
    if (!Array.isArray(saved)) return allKeys
    const savedSet = new Set(saved)
    return allKeys.filter((k) => savedSet.has(k))
  } catch {
    return allKeys
  }
}

export function saveTypeFilter(keys: string[]): void {
  localStorage.setItem(ORION_TYPE_FILTER_KEY, JSON.stringify(keys))
}

/** Tipos del nodo focal y de sus vecinos directos (para ver relaciones al enfocar). */
export function collectOrionFocusTypeKeys(
  entityId: string,
  allNodes: OrionGraphNode[],
  allLinks: OrionGraphLink[],
): string[] {
  const keys = new Set<string>()
  const focus = allNodes.find((n) => n.id === entityId)
  if (!focus) return []
  const focusKey = typeKeyFromFullType(focus.type || '')
  if (focusKey) keys.add(focusKey)

  for (const l of allLinks) {
    const s = (l.source as OrionGraphNode).id ?? (l.source as string)
    const t = (l.target as OrionGraphNode).id ?? (l.target as string)
    if (s !== entityId && t !== entityId) continue
    const otherId = s === entityId ? (t as string) : (s as string)
    const other = allNodes.find((n) => n.id === otherId)
    if (!other) continue
    const k = typeKeyFromFullType(other.type || '')
    if (k) keys.add(k)
  }
  return [...keys]
}

/** Activa tipos del subgrafo focal sin quitar el filtro guardado por el usuario. */
export function mergeOrionActiveKeysForFocus(
  entityId: string,
  allNodes: OrionGraphNode[],
  allLinks: OrionGraphLink[],
  activeTypeKeys: string[],
  allTypeKeys: string[],
): string[] {
  const focusKeys = collectOrionFocusTypeKeys(entityId, allNodes, allLinks)
  if (!focusKeys.length) return activeTypeKeys
  const merged = new Set(activeTypeKeys)
  for (const k of focusKeys) {
    if (allTypeKeys.includes(k)) merged.add(k)
  }
  return [...merged]
}
