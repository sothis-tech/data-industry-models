import { describe, it, expect, vi, beforeEach } from 'vitest'
import {
  fetchOrionEntitiesPage,
  fetchAllOrionEntities,
  uniqueEntitiesById,
  ORION_ENTITIES_PAGE_SIZE,
} from '../../lib/orion-entities'
import { getEntities } from '../../api/orion'

vi.mock('../../api/orion', () => ({
  getEntities: vi.fn(),
}))

const mockGetEntities = vi.mocked(getEntities)

describe('uniqueEntitiesById', () => {
  it('deduplicates by id keeping last occurrence', () => {
    const result = uniqueEntitiesById([
      { id: 'urn:ngsi-ld:A:1', type: 'A' },
      { id: 'urn:ngsi-ld:A:1', type: 'A2' },
      { id: 'urn:ngsi-ld:B:1', type: 'B' },
    ])
    expect(result).toHaveLength(2)
    expect(result.find((e) => e.id === 'urn:ngsi-ld:A:1')?.type).toBe('A2')
  })
})

describe('fetchOrionEntitiesPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('requests limit and offset', async () => {
    mockGetEntities.mockResolvedValue({
      status: 200,
      error: null,
      body: [{ id: 'urn:ngsi-ld:X:1', type: 'X' }],
    })

    await fetchOrionEntitiesPage('http://broker', { offset: 500, tenant: 't1' })

    expect(mockGetEntities).toHaveBeenCalledWith('http://broker', {
      limit: ORION_ENTITIES_PAGE_SIZE,
      offset: 500,
      type: undefined,
      tenant: 't1',
    })
  })

  it('sets hasMore when page is full', async () => {
    const body = Array.from({ length: ORION_ENTITIES_PAGE_SIZE }, (_, i) => ({
      id: `urn:ngsi-ld:E:${i}`,
      type: 'E',
    }))
    mockGetEntities.mockResolvedValue({ status: 200, error: null, body })

    const result = await fetchOrionEntitiesPage('http://broker')
    expect(result.hasMore).toBe(true)
    expect(result.entities).toHaveLength(ORION_ENTITIES_PAGE_SIZE)
  })
})

describe('fetchAllOrionEntities', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('fetches all pages until a short response', async () => {
    const page1 = Array.from({ length: ORION_ENTITIES_PAGE_SIZE }, (_, i) => ({
      id: `urn:ngsi-ld:E:${i}`,
      type: 'E',
    }))
    const page2 = [{ id: 'urn:ngsi-ld:E:last', type: 'E' }]

    mockGetEntities
      .mockResolvedValueOnce({ status: 200, error: null, body: page1 })
      .mockResolvedValueOnce({ status: 200, error: null, body: page2 })

    const progress: number[] = []
    const result = await fetchAllOrionEntities('http://broker', {
      onProgress: (n) => progress.push(n),
    })

    expect(mockGetEntities).toHaveBeenCalledTimes(2)
    expect(result.entities).toHaveLength(ORION_ENTITIES_PAGE_SIZE + 1)
    expect(result.error).toBeNull()
    expect(progress[progress.length - 1]).toBe(ORION_ENTITIES_PAGE_SIZE + 1)
  })

  it('returns partial data when a later page fails', async () => {
    const fullPage = Array.from({ length: ORION_ENTITIES_PAGE_SIZE }, (_, i) => ({
      id: `urn:ngsi-ld:E:${i}`,
      type: 'E',
    }))
    mockGetEntities
      .mockResolvedValueOnce({ status: 200, error: null, body: fullPage })
      .mockResolvedValueOnce({ status: 500, error: 'timeout', body: [] })

    const result = await fetchAllOrionEntities('http://broker')
    expect(result.entities).toHaveLength(ORION_ENTITIES_PAGE_SIZE)
    expect(result.error).toBe('timeout')
  })
})
