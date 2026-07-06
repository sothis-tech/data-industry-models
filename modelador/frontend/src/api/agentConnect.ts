import { API_BASE, networkError, parseProxyEnvelope, readJson } from '../lib/http'
import type { AgentConnectResult } from '../types/agentConnect'

export async function postAgentConnect(
  ngsildTenant: string,
  brokerBaseUrl: string,
): Promise<{ status: number; body: AgentConnectResult; error: string | null }> {
  try {
    const res = await fetch(`${API_BASE}/api/connect`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        ngsild_tenant: ngsildTenant,
        broker_base_url: brokerBaseUrl,
      }),
    })
    const data = await readJson<{
      status?: number
      body?: AgentConnectResult
      error?: string | null
    }>(res, {})
    return parseProxyEnvelope(res, data, {} as AgentConnectResult)
  } catch (e) {
    const message = e instanceof Error ? e.message : String(e)
    return networkError(message, {} as AgentConnectResult)
  }
}

export function formatAgentConnectStatus(body: AgentConnectResult): string {
  const parts: string[] = []
  if (body.orion?.status) {
    const o = body.orion
    const extra =
      o.types != null && o.total_entities != null
        ? ` (${o.types} tipos, ${o.total_entities} entidades)`
        : ''
    parts.push(`Orion: ${o.status}${extra}`)
  }
  if (body.rag?.status) {
    const r = body.rag
    const extra =
      r.documents != null && r.total_chunks != null
        ? ` (${r.documents} docs, ${r.total_chunks} chunks)`
        : ''
    parts.push(`RAG: ${r.status}${extra}`)
  }
  if (body.quantumleap?.status) {
    parts.push(`QuantumLeap: ${body.quantumleap.status}`)
  }
  return parts.length ? parts.join(' · ') : body.status || 'connected'
}
