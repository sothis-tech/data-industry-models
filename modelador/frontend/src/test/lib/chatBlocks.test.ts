import { describe, expect, it } from 'vitest'
import { normalizeEntityRow, parseChatBlocks } from '../../lib/chatBlocks'

describe('parseChatBlocks', () => {
  it('parses entity list from entities array', () => {
    const blocks = parseChatBlocks({
      entities: [
        { id: 'urn:ngsi-ld:Device:1', type: 'Device', name: { value: 'Sensor A' } },
      ],
    })
    expect(blocks).toHaveLength(1)
    expect(blocks[0]).toMatchObject({
      kind: 'entity-list',
      entities: [{ id: 'urn:ngsi-ld:Device:1', type: 'Device', name: 'Sensor A' }],
    })
  })

  it('parses json entity block', () => {
    const entity = { id: 'urn:ngsi-ld:X:1', type: 'X' }
    const blocks = parseChatBlocks({ entity })
    expect(blocks.some((b) => b.kind === 'json')).toBe(true)
  })

  it('parses graph from relationships', () => {
    const blocks = parseChatBlocks({
      relationships: [
        { source: 'urn:a', target: 'urn:b', label: 'ref' },
      ],
    })
    const graph = blocks.find((b) => b.kind === 'graph')
    expect(graph).toBeDefined()
    if (graph?.kind === 'graph') {
      expect(graph.edges).toHaveLength(1)
      expect(graph.nodes.length).toBeGreaterThanOrEqual(2)
    }
  })

  it('parses explicit blocks array', () => {
    const blocks = parseChatBlocks({
      blocks: [
        { kind: 'entity-list', entities: [{ id: 'urn:ngsi-ld:A:1', type: 'A' }] },
      ],
    })
    expect(blocks[0]?.kind).toBe('entity-list')
  })
})

describe('normalizeEntityRow', () => {
  it('returns null without id', () => {
    expect(normalizeEntityRow({ type: 'X' })).toBeNull()
  })
})
