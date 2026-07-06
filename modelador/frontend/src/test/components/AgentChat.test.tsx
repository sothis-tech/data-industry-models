import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import React from 'react'
import { AgentChat } from '../../components/AgentChat'

vi.mock('../../api/chat', () => ({
  getChatConfig: vi.fn(),
  sendChatText: vi.fn(),
}))

vi.mock('../../hooks/useAeaVoiceChat', () => ({
  useAeaVoiceChat: vi.fn(() => ({
    status: 'idle',
    error: null,
    isRecording: false,
    isConfigured: false,
    startRecording: vi.fn().mockResolvedValue(undefined),
    stopRecording: vi.fn(),
    resetVoiceSession: vi.fn(),
  })),
}))

import { getChatConfig, sendChatText } from '../../api/chat'

const mockGetChatConfig = vi.mocked(getChatConfig)
const mockSendChatText = vi.mocked(sendChatText)

const BROKER = { url: 'http://kong:8000', name: 'Kong', tenant: 'qa-tenant' }

function renderChat(overrides?: Partial<Parameters<typeof AgentChat>[0]>) {
  return render(
    <AgentChat
      broker={BROKER}
      isOrionAuthenticated
      isPanelOpen
      {...overrides}
    />,
  )
}

describe('AgentChat', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    Element.prototype.scrollTo = vi.fn()
    mockGetChatConfig.mockResolvedValue({ aea_ws_url: '', text_chat_enabled: true })
  })

  it('deshabilita el textarea mientras envía y lo rehabilita al terminar', async () => {
    let finishSend!: () => void
    mockSendChatText.mockImplementation(
      () =>
        new Promise((resolve) => {
          finishSend = () =>
            resolve({
              status: 200,
              error: null,
              body: { text: 'Respuesta de prueba', session_id: 'sess-1' },
            })
        }),
    )

    renderChat()
    const input = await screen.findByRole('textbox', { name: /mensaje para marvin/i })
    await waitFor(() => expect(input).toBeEnabled())

    fireEvent.change(input, { target: { value: 'Hola Marvin' } })
    fireEvent.submit(input.closest('form')!)

    await waitFor(() => expect(input).toBeDisabled())
    finishSend()
    await waitFor(() => expect(input).toBeEnabled())
  })

  it('restaura el foco en el textarea al terminar el envío', async () => {
    mockSendChatText.mockResolvedValue({
      status: 200,
      error: null,
      body: { text: 'Respuesta de prueba', session_id: 'sess-1' },
    })

    renderChat()
    const input = await screen.findByRole('textbox', { name: /mensaje para marvin/i })
    await waitFor(() => expect(input).toBeEnabled())

    fireEvent.change(input, { target: { value: 'Hola Marvin' } })
    fireEvent.submit(input.closest('form')!)

    await waitFor(() => expect(input).toBeEnabled())
    await waitFor(() => expect(input).toHaveFocus())
    expect(screen.getByText('Respuesta de prueba')).toBeInTheDocument()
  })

  it('un 401 del backend reinicia el historial con mensaje de sesión expirada', async () => {
    mockSendChatText.mockResolvedValue({
      status: 401,
      error: 'Unauthorized',
      body: { text: '', session_id: '' },
    })

    renderChat()
    const input = await screen.findByRole('textbox', { name: /mensaje para marvin/i })
    await waitFor(() => expect(input).toBeEnabled())

    fireEvent.change(input, { target: { value: 'Hola' } })
    fireEvent.submit(input.closest('form')!)

    await waitFor(() =>
      expect(screen.getByText(/sesión orion expirada/i)).toBeInTheDocument(),
    )
  })

  it('error de red muestra mensaje de error sin crashear', async () => {
    mockSendChatText.mockResolvedValue({
      status: 500,
      error: 'Internal Server Error',
      body: { text: '', session_id: '' },
    })

    renderChat()
    const input = await screen.findByRole('textbox', { name: /mensaje para marvin/i })
    await waitFor(() => expect(input).toBeEnabled())

    fireEvent.change(input, { target: { value: 'Hola' } })
    fireEvent.submit(input.closest('form')!)

    await waitFor(() =>
      expect(screen.getByText(/internal server error/i)).toBeInTheDocument(),
    )
  })

  it('con isOrionAuthenticated=false el textarea está bloqueado', async () => {
    renderChat({ isOrionAuthenticated: false })
    const input = await screen.findByRole('textbox', { name: /mensaje para marvin/i })
    expect(input).toBeDisabled()
  })

  it('cambio de tenant reinicia el historial', async () => {
    const { rerender } = renderChat()
    await screen.findByRole('textbox', { name: /mensaje para marvin/i })

    rerender(
      <AgentChat
        broker={{ url: 'http://kong:8000', name: 'Kong', tenant: 'otro-tenant' }}
        isOrionAuthenticated
        isPanelOpen
      />,
    )

    await waitFor(() =>
      expect(screen.getByText(/¡Hola! Soy Marvin/i)).toBeInTheDocument(),
    )
  })
})
