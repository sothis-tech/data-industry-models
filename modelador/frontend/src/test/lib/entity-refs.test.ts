import { describe, expect, it } from 'vitest'
import { findIncomingRelationshipRefs } from '../../lib/entity-refs'

describe('findIncomingRelationshipRefs', () => {
  const target = 'urn:ngsi-ld:Person:joaquin'

  it('encuentra Relationship que apunta al target', () => {
    const entities = [
      {
        id: 'urn:ngsi-ld:Op:1',
        type: 'Op',
        operator: { type: 'Relationship', object: target },
      },
      { id: target, type: 'Person' },
    ]
    const refs = findIncomingRelationshipRefs(entities, target)
    expect(refs).toHaveLength(1)
    expect(refs[0].entityId).toBe('urn:ngsi-ld:Op:1')
    expect(refs[0].attrName).toBe('operator')
    expect(refs[0].remainingObjects).toEqual([])
  })

  it('conserva otros objects en relaciones multi-valor', () => {
    const other = 'urn:ngsi-ld:Person:ana'
    const entities = [
      {
        id: 'urn:ngsi-ld:Op:1',
        type: 'Op',
        operators: { type: 'Relationship', object: [target, other] },
      },
    ]
    const refs = findIncomingRelationshipRefs(entities, target)
    expect(refs).toHaveLength(1)
    expect(refs[0].remainingObjects).toEqual([other])
  })

  it('ignora entidades sin relación al target', () => {
    const entities = [
      {
        id: 'urn:ngsi-ld:Op:1',
        type: 'Op',
        operator: { type: 'Relationship', object: 'urn:ngsi-ld:Person:otro' },
      },
    ]
    expect(findIncomingRelationshipRefs(entities, target)).toEqual([])
  })
})
