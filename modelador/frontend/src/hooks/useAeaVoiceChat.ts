import { useCallback, useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import type { AeaServerMessage, AeaStatus } from '../types/chat'

const TARGET_SAMPLE_RATE = 16_000
/** El VAD del voice-agent asume cada mensaje WS = exactamente 20 ms de audio (véase vad_manager.py). @ 16 kHz → 320 muestras int16. */
const SAMPLES_PER_WS_FRAME = Math.round((TARGET_SAMPLE_RATE * 20) / 1000)

type UseAeaVoiceChatOptions = {
  wsUrl: string
  onTranscript: (text: string) => void
  onResponse: (text: string, data?: Record<string, unknown>) => void
  onStatus: (text: string) => void
}

function downsampleBuffer(input: Float32Array, inputRate: number, outputRate: number): Float32Array {
  if (outputRate >= inputRate) return input
  const ratio = inputRate / outputRate
  const outputLength = Math.round(input.length / ratio)
  const output = new Float32Array(outputLength)
  let inputOffset = 0

  for (let i = 0; i < outputLength; i += 1) {
    const nextOffset = Math.round((i + 1) * ratio)
    let accum = 0
    let count = 0

    for (let j = inputOffset; j < nextOffset && j < input.length; j += 1) {
      accum += input[j]
      count += 1
    }

    output[i] = count > 0 ? accum / count : 0
    inputOffset = nextOffset
  }

  return output
}

function floatTo16BitPcmInt16(input: Float32Array): Int16Array {
  const out = new Int16Array(input.length)
  for (let i = 0; i < input.length; i += 1) {
    const clamped = Math.max(-1, Math.min(1, input[i]))
    out[i] = clamped < 0 ? Math.round(clamped * 0x8000) : Math.round(clamped * 0x7fff)
  }
  return out
}

function concatInt16(a: Int16Array, b: Int16Array): Int16Array {
  if (a.length === 0) return b
  const r = new Int16Array(a.length + b.length)
  r.set(a, 0)
  r.set(b, a.length)
  return r
}

function playBase64Wav(base64: string): void {
  const audio = new Audio(`data:audio/wav;base64,${base64}`)
  void audio.play().catch(() => {
    // El navegador puede bloquear autoplay; el texto queda visible igualmente.
  })
}

export function useAeaVoiceChat({ wsUrl, onTranscript, onResponse, onStatus }: UseAeaVoiceChatOptions) {
  const { t } = useTranslation()
  const [status, setStatus] = useState<AeaStatus>('idle')
  const [error, setError] = useState<string | null>(null)
  const [isRecording, setIsRecording] = useState(false)

  const wsRef = useRef<WebSocket | null>(null)
  const streamRef = useRef<MediaStream | null>(null)
  const audioContextRef = useRef<AudioContext | null>(null)
  const sourceRef = useRef<MediaStreamAudioSourceNode | null>(null)
  const processorRef = useRef<ScriptProcessorNode | null>(null)
  const lastTranscriptRef = useRef('')
  /** Cola de muestras int16 @ 16 kHz hasta completar tramas de 20 ms para el servidor. */
  const pending16Ref = useRef<Int16Array>(new Int16Array(0))

  const stopAudioGraph = useCallback(() => {
    processorRef.current?.disconnect()
    sourceRef.current?.disconnect()
    streamRef.current?.getTracks().forEach((track) => track.stop())
    void audioContextRef.current?.close()

    processorRef.current = null
    sourceRef.current = null
    streamRef.current = null
    audioContextRef.current = null
    pending16Ref.current = new Int16Array(0)
    setIsRecording(false)
  }, [])

  const closeSocket = useCallback(() => {
    const ws = wsRef.current
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.close()
    }
    wsRef.current = null
  }, [])

  const handleServerMessage = useCallback((event: MessageEvent<string>) => {
    let message: AeaServerMessage
    try {
      message = JSON.parse(event.data) as AeaServerMessage
    } catch {
      onStatus(event.data)
      return
    }

    if (message.event === 'status_change') {
      if (message.status === 'processing') setStatus('processing')
      if (message.status === 'ready') setStatus('ready')
      return
    }

    if (message.event === 'ignored_noise') {
      onStatus(message.message || t('agent.voice.audioDiscarded'))
      return
    }

    const transcript = (message.transcript || '').trim()
    if (transcript && transcript !== lastTranscriptRef.current) {
      lastTranscriptRef.current = transcript
      onTranscript(transcript)
    }

    // Modelador: chat con `text` (markdown); `response` duplica `speech` para gafas, no usar aquí.
    const displayText = (
      (typeof message.text === 'string' ? message.text : '') ||
      (typeof message.speech === 'string' ? message.speech : '') ||
      ''
    ).trim()
    if (displayText) {
      const data =
        message.data && typeof message.data === 'object' && !Array.isArray(message.data)
          ? (message.data as Record<string, unknown>)
          : undefined
      onResponse(displayText, data)
    }

    if (message.audio) {
      playBase64Wav(message.audio)
    }
  }, [onResponse, onStatus, onTranscript, t])

  const ensureSocket = useCallback(async (): Promise<WebSocket> => {
    if (!wsUrl) {
      throw new Error(t('agent.voice.wsNotConfigured'))
    }

    const existing = wsRef.current
    if (existing && existing.readyState === WebSocket.OPEN) {
      return existing
    }

    setStatus('connecting')
    return new Promise((resolve, reject) => {
      const ws = new WebSocket(wsUrl)
      ws.binaryType = 'arraybuffer'
      wsRef.current = ws

      ws.onopen = () => {
        ws.send(JSON.stringify({ mode: 'direct' }))
        resolve(ws)
      }
      ws.onmessage = handleServerMessage
      ws.onerror = () => {
        reject(new Error(t('agent.voice.connectFailed')))
      }
      ws.onclose = () => {
        if (isRecording) stopAudioGraph()
        setStatus((current) => (current === 'error' ? current : 'idle'))
      }
    })
  }, [handleServerMessage, isRecording, stopAudioGraph, wsUrl, t])

  const flushPendingFrames = useCallback((ws: WebSocket) => {
    const pending = pending16Ref.current
    if (pending.length === 0) return
    const mod = pending.length % SAMPLES_PER_WS_FRAME
    const pad = mod === 0 ? 0 : SAMPLES_PER_WS_FRAME - mod
    const padded = new Int16Array(pending.length + pad)
    padded.set(pending, 0)
    for (let o = 0; o < padded.length; o += SAMPLES_PER_WS_FRAME) {
      const frame = padded.subarray(o, o + SAMPLES_PER_WS_FRAME)
      const copy = new Int16Array(SAMPLES_PER_WS_FRAME)
      copy.set(frame)
      if (ws.readyState === WebSocket.OPEN) ws.send(copy.buffer)
    }
    pending16Ref.current = new Int16Array(0)
  }, [])

  const startRecording = useCallback(async () => {
    try {
      setError(null)
      lastTranscriptRef.current = ''
      pending16Ref.current = new Int16Array(0)
      const ws = await ensureSocket()
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          channelCount: 1,
          echoCancellation: true,
          noiseSuppression: true,
        },
      })
      const audioContext = new AudioContext()
      const source = audioContext.createMediaStreamSource(stream)
      const processor = audioContext.createScriptProcessor(4096, 1, 1)

      // Mismo patrón que voice_agent/chat.component: el processor debe ir a destino con gain 0 (sin eco).
      const silentGain = audioContext.createGain()
      silentGain.gain.value = 0
      source.connect(processor)
      processor.connect(silentGain)
      silentGain.connect(audioContext.destination)

      processor.onaudioprocess = (audioEvent) => {
        if (ws.readyState !== WebSocket.OPEN) return
        const channel = audioEvent.inputBuffer.getChannelData(0)
        const downsampled = downsampleBuffer(channel, audioContext.sampleRate, TARGET_SAMPLE_RATE)
        const int16Chunk = floatTo16BitPcmInt16(downsampled)
        pending16Ref.current = concatInt16(pending16Ref.current, int16Chunk)
        while (pending16Ref.current.length >= SAMPLES_PER_WS_FRAME) {
          const frame = pending16Ref.current.subarray(0, SAMPLES_PER_WS_FRAME)
          const copy = new Int16Array(SAMPLES_PER_WS_FRAME)
          copy.set(frame)
          ws.send(copy.buffer)
          pending16Ref.current = pending16Ref.current.subarray(SAMPLES_PER_WS_FRAME)
        }
      }

      streamRef.current = stream
      audioContextRef.current = audioContext
      sourceRef.current = source
      processorRef.current = processor
      setIsRecording(true)
      setStatus('recording')
    } catch (e) {
      const message = e instanceof Error ? e.message : String(e)
      setError(message)
      setStatus('error')
      stopAudioGraph()
      onStatus(message)
    }
  }, [ensureSocket, onStatus, stopAudioGraph])

  const stopRecording = useCallback(() => {
    const ws = wsRef.current
    if (ws && ws.readyState === WebSocket.OPEN) {
      flushPendingFrames(ws)
      ws.send('__END__')
      setStatus('processing')
    }
    stopAudioGraph()
  }, [flushPendingFrames, stopAudioGraph])

  /** Cierra micrófono y WebSocket (p. ej. al cerrar sesión Orion). */
  const resetVoiceSession = useCallback(() => {
    stopAudioGraph()
    closeSocket()
    lastTranscriptRef.current = ''
    pending16Ref.current = new Int16Array(0)
    setStatus('idle')
    setError(null)
  }, [closeSocket, stopAudioGraph])

  useEffect(() => {
    return () => {
      stopAudioGraph()
      closeSocket()
    }
  }, [closeSocket, stopAudioGraph])

  return {
    status,
    error,
    isConfigured: Boolean(wsUrl),
    isRecording,
    startRecording,
    stopRecording,
    resetVoiceSession,
  }
}
