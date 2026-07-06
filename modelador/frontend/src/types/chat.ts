import type { ChatBlock } from '../lib/chatBlocks'

export type ChatRole = 'user' | 'assistant' | 'system'

export type ChatSource = 'text' | 'voice' | 'status'

export type ChatMessage = {
  id: string
  role: ChatRole
  text: string
  source: ChatSource
  createdAt: number
  /** Bloques estructurados (listas, JSON, grafo) del campo `data` del agente. */
  blocks?: ChatBlock[]
}

export type ChatConfig = {
  aea_ws_url: string
  text_chat_enabled: boolean
}

export type ChatTextResult = {
  request_id?: string
  session_id?: string
  text?: string
  speech?: string
  data?: Record<string, unknown>
}

export type AeaStatus = 'idle' | 'connecting' | 'recording' | 'processing' | 'ready' | 'error'

export type AeaServerMessage = {
  event?: 'status_change' | 'ignored_noise' | string
  status?: string
  message?: string
  transcript?: string
  /** Texto para el chat (p. ej. Markdown); el modelador prioriza este campo */
  text?: string | null
  /** Guion para TTS; no usar como cuerpo principal del chat */
  speech?: string | null
  /** Igual que `speech` (clientes legacy gafas que solo leen `response`); el modelador usa `text`. */
  response?: string | null
  audio?: string | null
  data?: Record<string, unknown>
  meta?: {
    session_id?: string
    [key: string]: unknown
  }
}
