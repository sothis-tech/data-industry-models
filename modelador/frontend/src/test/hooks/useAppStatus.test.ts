import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { renderHook, act, waitFor } from '@testing-library/react'
import { useAppStatus } from '../../hooks/useAppStatus'
import { dispatchOrionSessionLost } from '../../lib/orionSessionEvents'

// ── Mocks ─────────────────────────────────────────────────────────────────────

vi.mock('../../api/orion', () => ({
  getOrionAuthStatus: vi.fn(),
}))

vi.mock('../../lib/storage', () => ({
  getCurrentBroker: vi.fn(),
}))

import { getOrionAuthStatus } from '../../api/orion'
import { getCurrentBroker } from '../../lib/storage'

const mockGetStatus = vi.mocked(getOrionAuthStatus)
const mockGetBroker = vi.mocked(getCurrentBroker)

const BROKER = { url: 'http://kong:8000', name: 'Kong', tenant: 'qa' }

// ── Tests ─────────────────────────────────────────────────────────────────────

describe('useAppStatus', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    localStorage.clear()
  })

  afterEach(() => {
    localStorage.clear()
  })

  it('health es "unknown" cuando no hay broker configurado', async () => {
    mockGetBroker.mockReturnValue(null)
    const { result } = renderHook(() => useAppStatus())
    await waitFor(() => expect(result.current.health).toBe('unknown'))
  })

  it('health es "ok" cuando el broker responde logged_in=true', async () => {
    mockGetBroker.mockReturnValue(BROKER)
    mockGetStatus.mockResolvedValue({ loggedIn: true })
    const { result } = renderHook(() => useAppStatus())
    await waitFor(() => expect(result.current.health).toBe('ok'))
  })

  it('health es "no-session" cuando el broker responde logged_in=false', async () => {
    mockGetBroker.mockReturnValue(BROKER)
    mockGetStatus.mockResolvedValue({ loggedIn: false })
    const { result } = renderHook(() => useAppStatus())
    await waitFor(() => expect(result.current.health).toBe('no-session'))
  })

  it('health es "error" cuando la llamada al broker falla', async () => {
    mockGetBroker.mockReturnValue(BROKER)
    mockGetStatus.mockRejectedValue(new Error('network error'))
    const { result } = renderHook(() => useAppStatus())
    await waitFor(() => expect(result.current.health).toBe('error'))
  })

  it('evento ORION_SESSION_LOST fuerza health a "no-session" sin recargar', async () => {
    mockGetBroker.mockReturnValue(BROKER)
    mockGetStatus.mockResolvedValue({ loggedIn: true })
    const { result } = renderHook(() => useAppStatus())
    await waitFor(() => expect(result.current.health).toBe('ok'))

    act(() => { dispatchOrionSessionLost('token expirado') })

    await waitFor(() => expect(result.current.health).toBe('no-session'))
  })

  it('model.loaded es false cuando localStorage no tiene modelo', () => {
    mockGetBroker.mockReturnValue(null)
    localStorage.removeItem('ngsi_model')
    const { result } = renderHook(() => useAppStatus())
    expect(result.current.model.loaded).toBe(false)
  })

  it('model refleja N tipos cuando hay schemas en localStorage', () => {
    mockGetBroker.mockReturnValue(null)
    localStorage.setItem(
      'ngsi_model',
      JSON.stringify({ schemas: [{ title: 'A' }, { title: 'B' }], context: null }),
    )
    const { result } = renderHook(() => useAppStatus())
    expect(result.current.model.loaded).toBe(true)
    expect(result.current.model.label).toBe('2 tipos')
  })

  it('model refleja "contexto cargado" cuando solo hay context sin schemas', () => {
    mockGetBroker.mockReturnValue(null)
    localStorage.setItem(
      'ngsi_model',
      JSON.stringify({ schemas: [], context: { '@context': {} } }),
    )
    const { result } = renderHook(() => useAppStatus())
    expect(result.current.model.loaded).toBe(true)
    expect(result.current.model.label).toBe('contexto cargado')
  })

  it('broker devuelto coincide con el del storage', async () => {
    mockGetBroker.mockReturnValue(BROKER)
    mockGetStatus.mockResolvedValue({ loggedIn: true })
    const { result } = renderHook(() => useAppStatus())
    await waitFor(() => expect(result.current.health).toBe('ok'))
    expect(result.current.broker).toEqual(BROKER)
  })

  it('polling con fake timers llama a getOrionAuthStatus periódicamente', async () => {
    vi.useFakeTimers()
    mockGetBroker.mockReturnValue(BROKER)
    mockGetStatus.mockResolvedValue({ loggedIn: true })

    renderHook(() => useAppStatus())
    // llamada inicial
    await act(async () => { await Promise.resolve() })
    const callsAfterMount = mockGetStatus.mock.calls.length

    // avanzar 90 s → debe haber un poll más
    await act(async () => { vi.advanceTimersByTime(90_000) })
    expect(mockGetStatus.mock.calls.length).toBeGreaterThan(callsAfterMount)

    vi.useRealTimers()
  })
})
