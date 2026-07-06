/**
 * Logs en una sola línea JSON por evento (consumible por agregadores / jq).
 *
 * - Siempre JSON en consola; usar DevTools → filtrar por nivel.
 * - VITE_LOG_FORMAT=text: mensaje legible (solo desarrollo).
 * - VITE_LOG_LEVEL=debug|info|warn|error: umbral mínimo (por defecto info).
 */

export type LogLevel = 'debug' | 'info' | 'warn' | 'error'

const SERVICE = 'modelador-web'

const LEVEL_RANK: Record<LogLevel, number> = {
  debug: 10,
  info: 20,
  warn: 30,
  error: 40,
}

function configuredMinRank(): number {
  try {
    const raw = (import.meta.env.VITE_LOG_LEVEL as string | undefined)?.trim().toLowerCase() ?? 'info'
    const map: Record<string, number> = {
      debug: 10,
      info: 20,
      warn: 30,
      warning: 30,
      error: 40,
    }
    return map[raw] ?? 20
  } catch {
    return 20
  }
}

function textFormatEnabled(): boolean {
  try {
    return import.meta.env.DEV && import.meta.env.VITE_LOG_FORMAT === 'text'
  } catch {
    return false
  }
}

function emit(level: LogLevel, message: string, meta?: Record<string, unknown>): void {
  if (LEVEL_RANK[level] < configuredMinRank()) return

  const payload: Record<string, unknown> = {
    ts: new Date().toISOString(),
    level,
    service: SERVICE,
    msg: message,
    ...meta,
  }

  if (textFormatEnabled()) {
    const suffix = meta && Object.keys(meta).length ? ` ${JSON.stringify(meta)}` : ''
    const line = `[${payload.ts}] ${level.toUpperCase()} ${message}${suffix}`
    switch (level) {
      case 'debug':
        console.debug(line)
        break
      case 'info':
        console.info(line)
        break
      case 'warn':
        console.warn(line)
        break
      default:
        console.error(line)
    }
    return
  }

  const line = JSON.stringify(payload)
  switch (level) {
    case 'debug':
      console.debug(line)
      break
    case 'info':
      console.info(line)
      break
    case 'warn':
      console.warn(line)
      break
    default:
      console.error(line)
  }
}

export const log = {
  debug: (msg: string, meta?: Record<string, unknown>) => emit('debug', msg, meta),
  info: (msg: string, meta?: Record<string, unknown>) => emit('info', msg, meta),
  warn: (msg: string, meta?: Record<string, unknown>) => emit('warn', msg, meta),
  error: (msg: string, meta?: Record<string, unknown>) => emit('error', msg, meta),
}
