import { describe, it, expect, beforeEach, afterEach } from 'vitest'
import {
  typeKeyFromFullType,
  collectOrionFocusTypeKeys,
  computeOrionFocusVisibleNodeIds,
  computeOrionVisibleNodeIds,
  contrastTextColor,
  filterOrionByTypeKeys,
  graphNodeCollisionRadius,
  loadSavedTypeFilter,
  mergeOrionActiveKeysForFocus,
  saveTypeFilter,
  splitGraphNodeLabel,
} from '../../lib/graph-utils'
import type { OrionGraphNode, OrionGraphLink } from '../../types/graph'

// ── typeKeyFromFullType ───────────────────────────────────────────────────────
// La implementación usa .split('/').pop(), por lo que solo extrae el último
// segmento de la ruta. Los fragmentos (#) no se procesan por separado.

describe('typeKeyFromFullType', () => {
  it('extracts the last path segment from a full IRI', () => {
    expect(typeKeyFromFullType('https://example.org/ManufacturingMachine')).toBe('ManufacturingMachine')
  })

  it('returns the value unchanged when it is already a short name', () => {
    expect(typeKeyFromFullType('Machine')).toBe('Machine')
  })

  it('returns the last segment of a multi-level IRI', () => {
    expect(typeKeyFromFullType('https://example.org/ontology/Device')).toBe('Device')
  })

  it('returns empty string for empty input', () => {
    expect(typeKeyFromFullType('')).toBe('')
  })

  it('handles URN-style types', () => {
    // urn:ngsi-ld:ManufacturingMachine → last segment after /
    const result = typeKeyFromFullType('urn:ngsi-ld:ManufacturingMachine')
    expect(typeof result).toBe('string')
  })
})

// ── filterOrionByTypeKeys ─────────────────────────────────────────────────────

const NODES: OrionGraphNode[] = [
  { id: 'urn:ngsi-ld:Machine:001', type: 'https://example.org/Machine',  label: 'M1' },
  { id: 'urn:ngsi-ld:Area:001',    type: 'https://example.org/Area',     label: 'A1' },
  { id: 'urn:ngsi-ld:Device:001',  type: 'https://example.org/Device',   label: 'D1' },
]

const LINKS: OrionGraphLink[] = [
  { source: 'urn:ngsi-ld:Machine:001', target: 'urn:ngsi-ld:Area:001',    property: 'locatedIn', implicit: false },
  { source: 'urn:ngsi-ld:Device:001',  target: 'urn:ngsi-ld:Machine:001', property: 'monitors',  implicit: false },
]

const ALL_KEYS = ['Machine', 'Area', 'Device']

describe('filterOrionByTypeKeys', () => {
  it('returns all nodes when all keys are active', () => {
    const { nodes } = filterOrionByTypeKeys(NODES, LINKS, ALL_KEYS, ALL_KEYS)
    expect(nodes).toHaveLength(3)
  })

  it('filters out nodes whose type key is not active', () => {
    const activeKeys = ['Machine', 'Area']
    const { nodes } = filterOrionByTypeKeys(NODES, LINKS, activeKeys, ALL_KEYS)
    const ids = nodes.map(n => n.id)
    expect(ids).not.toContain('urn:ngsi-ld:Device:001')
  })

  it('keeps links only when both endpoints are visible', () => {
    const activeKeys = ['Machine', 'Area']
    const { links } = filterOrionByTypeKeys(NODES, LINKS, activeKeys, ALL_KEYS)
    expect(links).toHaveLength(1)
    expect(links[0].property).toBe('locatedIn')
  })

  it('returns empty nodes and links when no keys are active', () => {
    const { nodes, links } = filterOrionByTypeKeys(NODES, LINKS, [], ALL_KEYS)
    expect(nodes).toHaveLength(0)
    expect(links).toHaveLength(0)
  })

  it('returns all nodes when all types are active', () => {
    const { nodes, links } = filterOrionByTypeKeys(NODES, LINKS, ALL_KEYS, ALL_KEYS)
    expect(nodes).toHaveLength(3)
    expect(links).toHaveLength(2)
  })

  it('removes links connected to hidden nodes', () => {
    const activeKeys = ['Device']  // solo Device activo
    const { links } = filterOrionByTypeKeys(NODES, LINKS, activeKeys, ALL_KEYS)
    // El link Device→Machine requiere que Machine sea visible → se elimina
    expect(links).toHaveLength(0)
  })
})

// ── computeOrionVisibleNodeIds ────────────────────────────────────────────────

describe('computeOrionVisibleNodeIds', () => {
  it('uses type filter when search draft is empty', () => {
    const ids = computeOrionVisibleNodeIds(NODES, LINKS, ['Machine'], ALL_KEYS, '')
    expect(ids.has('urn:ngsi-ld:Machine:001')).toBe(true)
    expect(ids.has('urn:ngsi-ld:Area:001')).toBe(false)
  })

  it('uses search matches when draft is non-empty', () => {
    const ids = computeOrionVisibleNodeIds(NODES, LINKS, ['Machine'], ALL_KEYS, 'area')
    expect(ids.has('urn:ngsi-ld:Area:001')).toBe(true)
    expect(ids.has('urn:ngsi-ld:Machine:001')).toBe(false)
  })

  it('shows all nodes when all types active and no search', () => {
    const ids = computeOrionVisibleNodeIds(NODES, LINKS, ALL_KEYS, ALL_KEYS, '')
    expect(ids.size).toBe(NODES.length)
  })
})

// ── computeOrionFocusVisibleNodeIds ───────────────────────────────────────────

describe('computeOrionFocusVisibleNodeIds', () => {
  it('includes focus node and type-filtered neighbors', () => {
    const ids = computeOrionFocusVisibleNodeIds(
      'urn:ngsi-ld:Machine:001',
      NODES,
      LINKS,
      ALL_KEYS,
      ALL_KEYS,
    )
    expect(ids.has('urn:ngsi-ld:Machine:001')).toBe(true)
    expect(ids.has('urn:ngsi-ld:Area:001')).toBe(true)
    expect(ids.has('urn:ngsi-ld:Device:001')).toBe(true)
  })

  it('hides neighbors whose type is not active', () => {
    const ids = computeOrionFocusVisibleNodeIds(
      'urn:ngsi-ld:Machine:001',
      NODES,
      LINKS,
      ['Machine'],
      ALL_KEYS,
    )
    expect(ids.has('urn:ngsi-ld:Machine:001')).toBe(true)
    expect(ids.has('urn:ngsi-ld:Area:001')).toBe(false)
  })
})

// ── collectOrionFocusTypeKeys / mergeOrionActiveKeysForFocus ───────────────────

describe('collectOrionFocusTypeKeys / mergeOrionActiveKeysForFocus', () => {
  it('includes focus node type and direct neighbor types', () => {
    const keys = collectOrionFocusTypeKeys('urn:ngsi-ld:Machine:001', NODES, LINKS)
    expect(keys).toContain('Machine')
    expect(keys).toContain('Area')
    expect(keys).toContain('Device')
  })

  it('merges focus types into active filter without removing saved keys', () => {
    const merged = mergeOrionActiveKeysForFocus(
      'urn:ngsi-ld:Machine:001',
      NODES,
      LINKS,
      ['Device'],
      ALL_KEYS,
    )
    expect(merged).toContain('Device')
    expect(merged).toContain('Machine')
    expect(merged).toContain('Area')
  })
})

// ── saveTypeFilter / loadSavedTypeFilter ──────────────────────────────────────
// loadSavedTypeFilter solo devuelve claves que están TANTO en allKeys
// como en el array guardado. Claves nuevas no están en el guardado → se excluyen.

describe('saveTypeFilter / loadSavedTypeFilter', () => {
  beforeEach(() => { localStorage.clear() })
  afterEach(() => { localStorage.clear() })

  it('saves and restores active keys', () => {
    saveTypeFilter(['Machine', 'Area'])
    const loaded = loadSavedTypeFilter(['Machine', 'Area', 'Device'])
    expect(loaded).toContain('Machine')
    expect(loaded).toContain('Area')
  })

  it('returns all keys when nothing is saved', () => {
    const allKeys = ['Machine', 'Area', 'Device']
    const loaded = loadSavedTypeFilter(allKeys)
    expect(loaded).toEqual(allKeys)
  })

  it('excludes keys not present in saved filter', () => {
    saveTypeFilter(['Machine'])  // Device fue deseleccionado
    const loaded = loadSavedTypeFilter(['Machine', 'Device'])
    expect(loaded).toContain('Machine')
    expect(loaded).not.toContain('Device')
  })

  it('excludes new keys not present at save time', () => {
    // El filtro guardado no conoce NewType → se excluye (usuario deberá activarlo)
    saveTypeFilter(['Machine'])
    const loaded = loadSavedTypeFilter(['Machine', 'Device', 'NewType'])
    expect(loaded).not.toContain('NewType')
    expect(loaded).not.toContain('Device')
  })

  it('returns empty array when saved filter is empty', () => {
    saveTypeFilter([])
    const loaded = loadSavedTypeFilter(['Machine', 'Device'])
    expect(loaded).toEqual([])
  })
})

describe('splitGraphNodeLabel', () => {
  it('returns a single line for short labels', () => {
    expect(splitGraphNodeLabel('ParkingLot')).toEqual(['ParkingLot'])
  })

  it('wraps long labels into multiple lines without ellipsis', () => {
    const lines = splitGraphNodeLabel('ManufacturingMachineAssemblyLineZone')
    expect(lines.length).toBeGreaterThan(1)
    expect(lines.join('')).toBe('ManufacturingMachineAssemblyLineZone')
    expect(lines.join('')).not.toContain('…')
  })

  it('keeps hyphenated ids intact on one line when short enough', () => {
    expect(splitGraphNodeLabel('robot-pintura-004')).toEqual(['robot-pintura-004'])
  })
})

describe('contrastTextColor', () => {
  it('returns dark text on light backgrounds', () => {
    expect(contrastTextColor('#ffff00')).toBe('#1f2328')
  })

  it('returns light text on dark backgrounds', () => {
    expect(contrastTextColor('#1a3050')).toBe('#ffffff')
  })
})

describe('graphNodeCollisionRadius', () => {
  it('grows with label line count when labels are below', () => {
    expect(graphNodeCollisionRadius(20, 1, 'below')).toBeLessThan(graphNodeCollisionRadius(20, 2, 'below'))
  })

  it('uses tighter radius when labels are inside the node', () => {
    expect(graphNodeCollisionRadius(20, 2, 'inside')).toBeLessThan(graphNodeCollisionRadius(20, 2, 'below'))
  })
})
