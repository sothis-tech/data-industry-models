import { beforeEach, describe, expect, it, vi } from 'vitest'
import { deleteEntityCascade } from '../../lib/entity-delete'

vi.mock('../../api/orion', () => ({
  getSubscriptions: vi.fn(),
  deleteSubscription: vi.fn(),
  deleteEntityAttr: vi.fn(),
  patchEntityAttrs: vi.fn(),
  deleteEntity: vi.fn(),
}))

vi.mock('../../lib/orion-entities', () => ({
  fetchAllOrionEntities: vi.fn(),
}))

import {
  deleteEntity,
  deleteEntityAttr,
  deleteSubscription,
  getSubscriptions,
  patchEntityAttrs,
} from '../../api/orion'

const mockGetSubscriptions = vi.mocked(getSubscriptions)
const mockDeleteSubscription = vi.mocked(deleteSubscription)
const mockDeleteEntityAttr = vi.mocked(deleteEntityAttr)
const mockPatchEntityAttrs = vi.mocked(patchEntityAttrs)
const mockDeleteEntity = vi.mocked(deleteEntity)

const TARGET = 'urn:ngsi-ld:Person:joaquin'
const BROKER = 'http://localhost:1026'

describe('deleteEntityCascade', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockDeleteEntity.mockResolvedValue({ status: 204, error: null, body: null })
    mockDeleteSubscription.mockResolvedValue({ status: 204, error: null, body: null })
    mockDeleteEntityAttr.mockResolvedValue({ status: 204, error: null, body: null })
    mockPatchEntityAttrs.mockResolvedValue({ status: 204, error: null, body: {} })
  })

  it('borra suscripciones QL y attrs entrantes antes de la entidad', async () => {
    mockGetSubscriptions.mockResolvedValue({
      status: 200,
      error: null,
      body: [
        {
          id: 'urn:ngsi-ld:Subscription:1',
          status: 'active',
          entities: [{ id: TARGET, type: 'Person' }],
          notification: { endpoint: { uri: 'http://quantumleap:8668/v2/notify' } },
        },
      ],
    })

    const knownEntities = [
      {
        id: 'urn:ngsi-ld:Op:1',
        type: 'Op',
        operator: { type: 'Relationship', object: TARGET },
      },
      { id: TARGET, type: 'Person' },
    ]

    const res = await deleteEntityCascade(BROKER, TARGET, {
      knownEntities,
      tenant: 'ibermot',
    })

    expect(res.error).toBeNull()
    expect(res.status).toBe(204)
    expect(mockDeleteSubscription).toHaveBeenCalledWith(BROKER, 'urn:ngsi-ld:Subscription:1', 'ibermot')
    expect(mockDeleteEntityAttr).toHaveBeenCalledWith(BROKER, 'urn:ngsi-ld:Op:1', 'operator', 'ibermot')
    expect(mockDeleteEntity).toHaveBeenCalledWith(BROKER, TARGET, 'ibermot')
    expect(mockPatchEntityAttrs).not.toHaveBeenCalled()
  })

  it('hace PATCH cuando la relación multi-valor tiene otros objects', async () => {
    mockGetSubscriptions.mockResolvedValue({ status: 200, error: null, body: [] })
    const other = 'urn:ngsi-ld:Person:ana'
    await deleteEntityCascade(BROKER, TARGET, {
      knownEntities: [
        {
          id: 'urn:ngsi-ld:Op:1',
          type: 'Op',
          operators: { type: 'Relationship', object: [TARGET, other] },
        },
      ],
    })
    expect(mockPatchEntityAttrs).toHaveBeenCalled()
    expect(mockDeleteEntityAttr).not.toHaveBeenCalled()
    const patchArg = mockPatchEntityAttrs.mock.calls[0][2] as Record<string, { object: string }>
    expect(patchArg.operators.object).toBe(other)
  })
})
