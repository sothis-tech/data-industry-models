import i18n from '../lib/i18n'
import { API_BASE, readJson } from '../lib/http'
export async function fetchViaProxy(url: string): Promise<unknown> {
  try {
    const res = await fetch(`${API_BASE}/api/proxy/fetch`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url }),
    })
    if (!res.ok) {
      const err = await readJson<{ detail?: string }>(res, {})
      throw new Error(err.detail || res.statusText)
    }
    return readJson<unknown>(res, null)
  } catch (e) {
    const message = e instanceof Error ? e.message : String(e)
    throw new Error(i18n.t('errors.model.loadUrl', { message }))
  }
}
export async function fetchManyViaProxy(urls: string[]): Promise<unknown[]> {
  try {
    const res = await fetch(`${API_BASE}/api/proxy/fetch`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ urls }),
    })
    const data = await readJson<{
      detail?: string
      results?: Array<{ ok: boolean; error?: string; url?: string; content?: unknown }>
    }>(res, {})
    if (!res.ok) throw new Error(data.detail || res.statusText)
    if (!data.results) throw new Error(i18n.t('errors.model.invalidProxyResponse'))
    const out: unknown[] = []
    for (const r of data.results) {
      if (!r.ok) throw new Error((r.error || i18n.t('errors.model.urlFailed', { url: r.url })) + (r.url ? ` (${r.url})` : ''))
      out.push(r.content)
    }
    return out
  } catch (e) {
    const message = e instanceof Error ? e.message : String(e)
    throw new Error(i18n.t('errors.model.loadUrls', { message }))
  }
}
export async function uploadModelPackage(file: File): Promise<{
  schemas?: unknown[]
  context?: unknown
  descriptor?: unknown
  examples?: Record<string, unknown>
  summary: {
    schemas: number
    context: boolean
    descriptor: boolean
    examples: number
    unrecognized?: unknown[]
  }
}> {
  const formData = new FormData()
  formData.append('file', file)
  try {
    const res = await fetch(`${API_BASE}/api/upload/model-package`, {
      method: 'POST',
      body: formData,
    })
    const data = await readJson<{ detail?: string } & Record<string, unknown>>(res, {})
    if (!res.ok) throw new Error(data.detail || i18n.t('errors.model.processPackage'))
    return data as {
      schemas?: unknown[]
      context?: unknown
      descriptor?: unknown
      examples?: Record<string, unknown>
      summary: {
        schemas: number
        context: boolean
        descriptor: boolean
        examples: number
        unrecognized?: unknown[]
      }
    }
  } catch (e) {
    const message = e instanceof Error ? e.message : String(e)
    throw new Error(i18n.t('errors.model.uploadPackage', { message }))
  }
}
