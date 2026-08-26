import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import type { TFunction } from 'i18next'
import { getChatConfig, sendChatText } from '../api/chat'
import { parseChatBlocks } from '../lib/chatBlocks'
import { useAeaVoiceChat } from '../hooks/useAeaVoiceChat'
import { resolveAeaWebSocketUrl } from '../lib/aeaWs'
import type { ChatConfig, ChatMessage } from '../types/chat'
import type { StoredBroker } from '../types/broker'
import { HeadsetIcon } from './AgentIcons'
import { AgentMessageBlocks } from './AgentMessageBlocks'
import { ChatMarkdown } from './ChatMarkdown'

function newMessage(
  role: ChatMessage['role'],
  text: string,
  source: ChatMessage['source'],
  blocks?: ChatMessage['blocks'],
): ChatMessage {
  return { id: crypto.randomUUID(), role, text, source, createdAt: Date.now(), blocks }
}

function statusLabel(status: string, t: TFunction): string {
  if (status === 'recording') return `● ${t('agent.chat.status.recording')}`
  if (status === 'processing') return `◌ ${t('agent.chat.status.processing')}`
  if (status === 'connecting') return `◌ ${t('agent.chat.status.connecting')}`
  if (status === 'ready') return `● ${t('agent.chat.status.ready')}`
  if (status === 'error') return `✕ ${t('agent.chat.status.error')}`
  return t('agent.chat.status.idle')
}

function MicIcon() {
  return (
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none"
      stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"
      aria-hidden="true">
      <path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z" />
      <path d="M19 10v2a7 7 0 0 1-14 0v-2" />
      <line x1="12" y1="19" x2="12" y2="23" />
      <line x1="8" y1="23" x2="16" y2="23" />
    </svg>
  )
}

function SendIcon() {
  return (
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none"
      stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"
      aria-hidden="true">
      <line x1="22" y1="2" x2="11" y2="13" />
      <polygon points="22 2 15 22 11 13 2 9 22 2" />
    </svg>
  )
}

function TypingDots() {
  return (
    <article className="chatbot-message chatbot-message--assistant chatbot-message--typing">
      <span /><span /><span />
    </article>
  )
}

type Props = {
  broker: StoredBroker | null
  isOrionAuthenticated: boolean
  isPanelOpen: boolean
}

export function AgentChat({ broker, isOrionAuthenticated, isPanelOpen }: Props) {
  const { t } = useTranslation()
  const [input, setInput] = useState('')
  const [isSending, setIsSending] = useState(false)
  const [config, setConfig] = useState<ChatConfig>({ aea_ws_url: '', text_chat_enabled: false })

  const initialChatMessages = useCallback((): ChatMessage[] => {
    return [newMessage('assistant', t('agent.chat.welcome'), 'status')]
  }, [t])

  const [messages, setMessages] = useState<ChatMessage[]>(() => [
    newMessage('assistant', t('agent.chat.welcome'), 'status'),
  ])
  const sessionIdRef = useRef<string>(crypto.randomUUID())
  const bodyRef = useRef<HTMLDivElement | null>(null)
  const inputRef = useRef<HTMLTextAreaElement | null>(null)
  const prevSendingRef = useRef(false)
  const prevAuthedRef = useRef<boolean | null>(null)
  const prevTenantKeyRef = useRef<string | null>(null)

  const tenantKey =
    broker?.url && broker?.tenant ? `${broker.url}\0${broker.tenant}` : null

  const appendAssistant = useCallback((text: string, source: ChatMessage['source'], data?: Record<string, unknown>) => {
    const trimmed = text.trim()
    if (!trimmed) return
    const blocks = parseChatBlocks(data)
    setMessages((current) => [...current, newMessage('assistant', trimmed, source, blocks.length ? blocks : undefined)])
  }, [])

  const appendMessage = useCallback((role: ChatMessage['role'], text: string, source: ChatMessage['source']) => {
    const trimmed = text.trim()
    if (!trimmed) return
    setMessages((current) => [...current, newMessage(role, trimmed, source)])
  }, [])

  const aeaWsResolved = useMemo(
    () => resolveAeaWebSocketUrl(config.aea_ws_url, broker?.url, broker?.tenant),
    [broker?.tenant, broker?.url, config.aea_ws_url],
  )

  const voice = useAeaVoiceChat({
    wsUrl: aeaWsResolved,
    onTranscript: (text) => appendMessage('user', text, 'voice'),
    onResponse: (text, data) => appendAssistant(text, 'voice', data),
    onStatus: (text) => appendMessage('system', text, 'status'),
  })

  const resetChatHistoryStable = useCallback((systemNote?: string) => {
    voice.resetVoiceSession()
    sessionIdRef.current = crypto.randomUUID()
    setInput('')
    setIsSending(false)
    setMessages(
      systemNote
        ? [...initialChatMessages(), newMessage('system', systemNote, 'status')]
        : initialChatMessages(),
    )
  }, [voice, initialChatMessages])

  // Reiniciar historial al cerrar sesión Orion o al cambiar de tenant/conexión.
  useEffect(() => {
    const hadTenant = prevTenantKeyRef.current !== null
    if (hadTenant && tenantKey !== prevTenantKeyRef.current) {
      resetChatHistoryStable(
        tenantKey
          ? t('agent.chat.system.tenantChanged')
          : t('agent.chat.system.noConnection'),
      )
    }
    prevTenantKeyRef.current = tenantKey

    if (prevAuthedRef.current === true && !isOrionAuthenticated) {
      resetChatHistoryStable(t('agent.chat.system.sessionClosed'))
    }
    prevAuthedRef.current = isOrionAuthenticated
  }, [tenantKey, isOrionAuthenticated, resetChatHistoryStable, t])

  useEffect(() => {
    let cancelled = false
    getChatConfig()
      .then((nextConfig) => { if (!cancelled) setConfig(nextConfig) })
      .catch((e) => {
        const message = e instanceof Error ? e.message : String(e)
        if (!cancelled) appendMessage('system', t('agent.chat.system.configError', { message }), 'status')
      })
    return () => { cancelled = true }
  }, [appendMessage, t])

  useEffect(() => {
    if (!isPanelOpen) return
    bodyRef.current?.scrollTo({ top: bodyRef.current.scrollHeight, behavior: 'smooth' })
  }, [messages, isPanelOpen, isSending])

  const canSendText = useMemo(
    () => Boolean(input.trim()) && !isSending && config.text_chat_enabled && isOrionAuthenticated,
    [config.text_chat_enabled, input, isOrionAuthenticated, isSending],
  )

  const voiceStatus = statusLabel(voice.status, t)
  const isVoiceActive = voice.status === 'ready' || voice.status === 'recording' || voice.status === 'processing'
  const chatLocked = !isOrionAuthenticated
  const inputPlaceholder = chatLocked
    ? t('agent.chat.placeholder.locked')
    : config.text_chat_enabled
      ? t('agent.chat.placeholder.ready')
      : t('agent.chat.placeholder.unavailable')

  // Tras responder Marvin, el textarea vuelve a estar habilitado; recuperar foco para seguir escribiendo.
  useEffect(() => {
    const wasSending = prevSendingRef.current
    prevSendingRef.current = isSending
    if (!wasSending || isSending) return
    if (!isPanelOpen || chatLocked || !config.text_chat_enabled) return
    const id = requestAnimationFrame(() => inputRef.current?.focus())
    return () => cancelAnimationFrame(id)
  }, [isSending, isPanelOpen, chatLocked, config.text_chat_enabled])

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const text = input.trim()
    if (!text || isSending) return
    if (!isOrionAuthenticated || !broker?.url || !broker.tenant) {
      appendMessage('system', t('agent.chat.system.loginFirst'), 'status')
      return
    }
    setInput('')
    setIsSending(true)
    appendMessage('user', text, 'text')
    const result = await sendChatText(
      text,
      sessionIdRef.current,
      broker.url,
      broker.tenant,
    )
    if (result.error || result.status >= 400) {
      const msg = result.error || t('agent.chat.system.httpError', { status: result.status })
      appendMessage('system', msg, 'status')
      if (result.status === 401) {
        resetChatHistoryStable(t('agent.chat.system.sessionExpired'))
      }
    } else {
      if (result.body.session_id) sessionIdRef.current = String(result.body.session_id)
      const reply =
        (result.body.text || '').trim() ||
        (result.body.speech || '').trim() ||
        t('agent.chat.system.noReply')
      const data = result.body.data
      appendAssistant(reply, 'text', data && typeof data === 'object' ? data : undefined)
    }
    setIsSending(false)
  }

  async function handleMicClick() {
    if (voice.isRecording) { voice.stopRecording(); return }
    await voice.startRecording()
  }

  return (
    <div className="agent-panel-chat">
      <div className="agent-chat-status-row">
        <span className={`chatbot-status-dot ${isVoiceActive ? 'chatbot-status-dot--on' : ''}`} />
        <span className="chatbot-status-text">{voiceStatus}</span>
      </div>

      <div ref={bodyRef} className="chatbot-body agent-panel-messages" aria-live="polite">
        {messages.map((message) => (
          <article key={message.id} className={`chatbot-message chatbot-message--${message.role}${message.blocks?.length ? ' chatbot-message--rich' : ''}`}>
            {message.role === 'assistant' && (
              <div className="chatbot-bubble-avatar"><HeadsetIcon size={12} /></div>
            )}
            <div className="chatbot-bubble">
              {message.role === 'assistant' ? (
                message.text ? <ChatMarkdown content={message.text} /> : null
              ) : (
                <p className="chatbot-plain-text">{message.text}</p>
              )}
              {message.blocks && message.blocks.length > 0 && (
                <AgentMessageBlocks blocks={message.blocks} />
              )}
              {message.role !== 'system' && (
                <small>{message.source === 'voice' ? t('agent.chat.sourceVoice') : t('agent.chat.sourceText')}</small>
              )}
            </div>
          </article>
        ))}
        {isSending && <TypingDots />}
      </div>

      <form className="chatbot-input" onSubmit={handleSubmit}>
        <textarea
          ref={inputRef}
          rows={1}
          value={input}
          onChange={(event) => setInput(event.target.value)}
          onKeyDown={(event) => {
            if (event.key !== 'Enter') return
            if (event.shiftKey) return
            event.preventDefault()
            if (!canSendText) return
            event.currentTarget.form?.requestSubmit()
          }}
          placeholder={inputPlaceholder}
          disabled={chatLocked || !config.text_chat_enabled || isSending}
          aria-label={t('agent.chat.inputAria')}
        />
        <button type="submit" disabled={!canSendText} className="chatbot-send" aria-label={t('agent.chat.sendAria')}>
          <SendIcon />
        </button>
      </form>

      <div className="chatbot-actions">
        <button
          type="button"
          className={`chatbot-mic${voice.isRecording ? ' chatbot-mic--active' : ''}`}
          disabled={chatLocked || !voice.isConfigured}
          onClick={handleMicClick}
          aria-pressed={voice.isRecording}
          title={
            chatLocked
              ? t('agent.chat.mic.locked')
              : voice.isConfigured
                ? t('agent.chat.mic.toggle')
                : t('agent.chat.mic.unavailable')
          }
        >
          <MicIcon />
          <span>{voice.isRecording ? t('agent.chat.mic.stop') : t('agent.chat.mic.label')}</span>
        </button>
        {chatLocked && <span className="chatbot-error">{t('agent.chat.lockedError')}</span>}
        {voice.error && <span className="chatbot-error">{voice.error}</span>}
      </div>
    </div>
  )
}
