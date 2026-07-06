import { API_BASE, networkError, parseProxyEnvelope, readJson } from '../lib/http'
import { reportOrionAuthFailure } from '../lib/orionSessionEvents'
import type { ChatConfig, ChatTextResult } from '../types/chat'

function extractChatAuthError(data: Record<string, unknown>): string {
  if (typeof data.detail === 'string') return data.detail
  if (typeof data.error === 'string') return data.error
  return 'Sesión Orion requerida'
}

export async function getChatConfig(): Promise<ChatConfig> {
  const res = await fetch(`${API_BASE}/api/chat/config`)
  return readJson<ChatConfig>(res, { aea_ws_url: '', text_chat_enabled: false })
}

export async function sendChatText(
  message: string,
  sessionId?: string,
  brokerBaseUrl?: string,
  tenant?: string,
  context?: Record<string, unknown>,
): Promise<{ status: number; body: ChatTextResult; error: string | null }> {
  try {
    const body: Record<string, unknown> = {
      message,
      session_id: sessionId,
      broker_base_url: brokerBaseUrl,
      tenant,
    }
    if (context && Object.keys(context).length > 0) {
      body.context = context
    }
    const res = await fetch(`${API_BASE}/api/chat/text`, {
      method: 'POST',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })
    const data = await readJson<{ status?: number; body?: ChatTextResult; error?: string | null; detail?: string }>(
      res,
      {},
    )
    const envelope = parseProxyEnvelope(res, data, {})
    if (!envelope.error && !data.status && res.status === 401) {
      reportOrionAuthFailure(res.status, data, extractChatAuthError(data))
    }
    return envelope
  } catch (e) {
    const messageText = e instanceof Error ? e.message : String(e)
    return networkError(messageText, {})
  }
}
