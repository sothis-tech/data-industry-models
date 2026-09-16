import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import { useEntityList } from '../../hooks/useEntityList'

// ── Mock de api/orion ─────────────────────────────────────────────────────────
vi.mock('../../api/orion', () => ({
  getEntities: vi.fn(),
  getSubscriptions: vi.fn(),
}))

import { getEntities, getSubscriptions } from '../../api/orion'
const mockGetEntities = vi.mocked(getEntities)
const mockGetSubscriptions = vi.mocked(getSubscriptions)

// ── Fixtures ──────────────────────────────────────────────────────────────────
// getEntities devuelve ApiResult<{body:[]}> = { status, error, body }

const BROKER = 'http://localhost:1026'

const MODEL_JSON = JSON.stringify({
  schemas: [
    { $schema: 'https://json-schema.org/draft/2020-12/schema', title: 'Machine', type: 'object' },
    { $schema: 'https://json-schema.org/draft/2020-12/schema', title: 'Area', type: 'object' },
  ],
  context: { '@context': { Machine: 'https://example.org/Machine', Area: 'https://example.org/Area' } },
  descriptor: null,
  examples: {},
})

const E_MACHINE = { id: 'urn:ngsi-ld:Machine:001', type: 'https://example.org/Machine' }
const E_AREA    = { id: 'urn:ngsi-ld:Area:001',    type: 'https://example.org/Area' }

// Forma correcta del retorno de getEntities
function ok(body: unknown[] = []) {
  return { status: 200, error: null, body } as ReturnType<typeof getEntities> extends Promise<infer T> ? T : never
}

function err(msg: string) {
  return { status: 0, error: msg, body: [] } as ReturnType<typeof getEntities> extends Promise<infer T> ? T : never
}

// ── Tests ─────────────────────────────────────────────────────────────────────

describe('useEntityList', () => {

  beforeEach(() => {
    vi.clearAllMocks()
    mockGetSubscriptions.mockResolvedValue({ status: 200, error: null, body: [] })
  })

  // ── Sin broker — no pide nada ────────────────────────────────────────────

  it('no hace ninguna petición si brokerUrl es null', async () => {
    const { result } = renderHook(() => useEntityList(null, '', null, []))
    await act(async () => { await result.current.fetchEntities() })
    expect(mockGetEntities).not.toHaveBeenCalled()
  })

  it('no hace ninguna petición si brokerUrl es cadena vacía', async () => {
    const { result } = renderHook(() => useEntityList('', '', null, []))
    await act(async () => { await result.current.fetchEntities() })
    expect(mockGetEntities).not.toHaveBeenCalled()
  })

  it('el hook no auto-fetches al montar — fetchEntities debe llamarse explícitamente', () => {
    renderHook(() => useEntityList(BROKER, '', MODEL_JSON, ['Machine', 'Area']))
    expect(mockGetEntities).not.toHaveBeenCalled()
  })

  // ── Carga exitosa ────────────────────────────────────────────────────────

  it('llama getEntities al invocar fetchEntities', async () => {
    mockGetEntities.mockResolvedValue(ok([E_MACHINE, E_AREA]))
    const { result } = renderHook(() => useEntityList(BROKER, '', MODEL_JSON, ['Machine', 'Area']))
    await act(async () => { await result.current.fetchEntities() })
    expect(mockGetEntities).toHaveBeenCalled()
  })

  it('allEntities se rellena con los datos devueltos', async () => {
    mockGetEntities.mockResolvedValue(ok([E_MACHINE, E_AREA]))
    const { result } = renderHook(() => useEntityList(BROKER, '', MODEL_JSON, ['Machine', 'Area']))
    await act(async () => { await result.current.fetchEntities() })
    expect(result.current.allEntities).toHaveLength(2)
  })

  it('loading pasa de true a false tras la carga', async () => {
    mockGetEntities.mockResolvedValue(ok([E_MACHINE]))
    const { result } = renderHook(() => useEntityList(BROKER, '', MODEL_JSON, ['Machine']))
    const promise = act(async () => { await result.current.fetchEntities() })
    await promise
    expect(result.current.loading).toBe(false)
  })

  it('error es null tras carga exitosa', async () => {
    mockGetEntities.mockResolvedValue(ok([E_MACHINE]))
    const { result } = renderHook(() => useEntityList(BROKER, '', MODEL_JSON, ['Machine']))
    await act(async () => { await result.current.fetchEntities() })
    expect(result.current.error).toBeNull()
  })

  // ── Filtro por tipo ──────────────────────────────────────────────────────

  it('con typeFilter filtra en cliente sin nueva petición', async () => {
    mockGetEntities.mockResolvedValue(ok([E_MACHINE, E_AREA]))
    const { result } = renderHook(() => useEntityList(BROKER, 'Machine', MODEL_JSON, ['Machine', 'Area']))
    await act(async () => { await result.current.fetchEntities() })
    expect(result.current.allEntities).toHaveLength(2)
    expect(result.current.typeFilteredEntities).toHaveLength(1)
    expect(result.current.typeFilteredEntities[0].id).toBe('urn:ngsi-ld:Machine:001')
  })

  // ── Errores de red ───────────────────────────────────────────────────────

  it('error se rellena cuando la respuesta tiene error (con typeFilter)', async () => {
    // Con typeFilter, el hook usa el path directo que comprueba r.error
    mockGetEntities.mockResolvedValue(err('Sin conexión'))
    const { result } = renderHook(() => useEntityList(BROKER, 'Machine', MODEL_JSON, ['Machine']))
    await act(async () => { await result.current.fetchEntities() })
    expect(result.current.error).toBeTruthy()
  })

  it('getEntities que lanza excepción pone error de red', async () => {
    mockGetEntities.mockRejectedValue(new Error('Network error'))
    const { result } = renderHook(() => useEntityList(BROKER, '', MODEL_JSON, ['Machine']))
    await act(async () => { await result.current.fetchEntities() })
    expect(result.current.error).toBeTruthy()
  })

  // ── Búsqueda (filteredEntities) ──────────────────────────────────────────

  it('filteredEntities devuelve todo cuando search está vacío', async () => {
    mockGetEntities.mockResolvedValue(ok([E_MACHINE, E_AREA]))
    const { result } = renderHook(() => useEntityList(BROKER, '', MODEL_JSON, ['Machine', 'Area']))
    await act(async () => { await result.current.fetchEntities() })
    expect(result.current.filteredEntities).toHaveLength(2)
  })

  it('filteredEntities filtra por ID cuando hay búsqueda', async () => {
    mockGetEntities.mockResolvedValue(ok([E_MACHINE, E_AREA]))
    const { result } = renderHook(() => useEntityList(BROKER, '', MODEL_JSON, ['Machine', 'Area']))
    await act(async () => { await result.current.fetchEntities() })
    act(() => { result.current.setSearch('Machine:001') })
    expect(result.current.filteredEntities).toHaveLength(1)
    expect(result.current.filteredEntities[0].id).toBe('urn:ngsi-ld:Machine:001')
  })

  it('filteredEntities devuelve vacío si la búsqueda no coincide', async () => {
    mockGetEntities.mockResolvedValue(ok([E_MACHINE, E_AREA]))
    const { result } = renderHook(() => useEntityList(BROKER, '', MODEL_JSON, ['Machine', 'Area']))
    await act(async () => { await result.current.fetchEntities() })
    act(() => { result.current.setSearch('xxxxxxxxxxxxxxx') })
    expect(result.current.filteredEntities).toHaveLength(0)
  })

  it('setSearch actualiza el valor de search', async () => {
    mockGetEntities.mockResolvedValue(ok([]))
    const { result } = renderHook(() => useEntityList(BROKER, '', MODEL_JSON, []))
    await act(async () => { await result.current.fetchEntities() })
    act(() => { result.current.setSearch('test') })
    expect(result.current.search).toBe('test')
  })

  // ── fetchEntities limpia la búsqueda ─────────────────────────────────────

  it('fetchEntities limpia la búsqueda al recargar', async () => {
    mockGetEntities.mockResolvedValue(ok([E_MACHINE]))
    const { result } = renderHook(() => useEntityList(BROKER, '', MODEL_JSON, ['Machine']))
    await act(async () => { await result.current.fetchEntities() })
    act(() => { result.current.setSearch('algo') })
    expect(result.current.search).toBe('algo')
    await act(async () => { await result.current.fetchEntities() })
    expect(result.current.search).toBe('')
  })

  it('filtra por suscripción a QuantumLeap', async () => {
    mockGetEntities.mockResolvedValue(ok([E_MACHINE, E_AREA]))
    mockGetSubscriptions.mockResolvedValue({
      status: 200,
      error: null,
      body: [{
        id: 'urn:ngsi-ld:Subscription:1',
        status: 'active',
        entities: [{ id: E_MACHINE.id, type: 'Machine' }],
        notification: { endpoint: { uri: 'http://quantumleap:8668/v2/notify' } },
      }],
    })
    const { result } = renderHook(() => useEntityList(BROKER, '', MODEL_JSON, ['Machine', 'Area']))
    await act(async () => { await result.current.fetchEntities() })
    expect(result.current.filteredEntities).toHaveLength(2)
    act(() => { result.current.setSubscriptionFilter('subscribed') })
    expect(result.current.filteredEntities.map((e) => e.id)).toEqual([E_MACHINE.id])
    act(() => { result.current.setSubscriptionFilter('unsubscribed') })
    expect(result.current.filteredEntities.map((e) => e.id)).toEqual([E_AREA.id])
  })

})
