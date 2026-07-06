import type { RagConfig, RagUploadResult, RagDocuments } from '../types/rag'

export async function getRagConfig(): Promise<RagConfig> {
  const res = await fetch('/api/rag/config')
  if (!res.ok) throw new Error(`Error config RAG: ${res.status}`)
  return res.json() as Promise<RagConfig>
}

export async function listRagTenants(): Promise<{ tenants: string[] }> {
  const res = await fetch('/api/rag/tenants')
  if (!res.ok) throw new Error(`Error listando tenants: ${res.status}`)
  return res.json() as Promise<{ tenants: string[] }>
}

export async function createRagTenant(name: string): Promise<void> {
  const res = await fetch('/api/rag/tenants', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name }),
  })
  if (!res.ok) throw new Error(`Error creando tenant: ${res.status}`)
}

export async function deleteRagTenant(tenant: string): Promise<void> {
  const res = await fetch(`/api/rag/tenants/${encodeURIComponent(tenant)}`, { method: 'DELETE' })
  if (!res.ok) throw new Error(`Error eliminando tenant: ${res.status}`)
}

function authedTenantParams(tenant: string, brokerBaseUrl: string, orionTenant = tenant): string {
  const params = new URLSearchParams({
    tenant,
    broker_base_url: brokerBaseUrl,
    orion_tenant: orionTenant,
  })
  return params.toString()
}

export async function listRagDocuments(tenant: string, brokerBaseUrl: string, orionTenant?: string): Promise<RagDocuments> {
  const res = await fetch(`/api/rag/documents?${authedTenantParams(tenant, brokerBaseUrl, orionTenant)}`)
  if (!res.ok) throw new Error(`Error listando documentos: ${res.status}`)
  return res.json() as Promise<RagDocuments>
}

export async function deleteRagDocument(
  tenant: string,
  brokerBaseUrl: string,
  filename: string,
  deleteFile = false,
  orionTenant?: string,
): Promise<void> {
  const params = new URLSearchParams({
    tenant,
    broker_base_url: brokerBaseUrl,
    orion_tenant: orionTenant ?? tenant,
    delete_file: String(deleteFile),
  })
  const url = `/api/rag/documents/${encodeURIComponent(filename)}?${params.toString()}`
  const res = await fetch(url, { method: 'DELETE' })
  if (!res.ok) throw new Error(`Error eliminando documento: ${res.status}`)
}

export async function vectorizeRagTenant(
  tenant: string,
  brokerBaseUrl: string,
  orionTenant?: string,
): Promise<{ processed: number }> {
  const res = await fetch(`/api/rag/vectorize?${authedTenantParams(tenant, brokerBaseUrl, orionTenant)}`, { method: 'POST' })
  if (!res.ok) throw new Error(`Error vectorizando: ${res.status}`)
  return res.json() as Promise<{ processed: number }>
}

export async function clearRagIndex(tenant: string, brokerBaseUrl: string, orionTenant?: string): Promise<void> {
  const res = await fetch(`/api/rag/clear?${authedTenantParams(tenant, brokerBaseUrl, orionTenant)}`, { method: 'DELETE' })
  if (!res.ok) throw new Error(`Error vaciando índice: ${res.status}`)
}

export async function uploadRagDocument(
  file: File,
  tenant: string,
  brokerBaseUrl: string,
  collection = 'documents',
  onProgress?: (pct: number) => void,
  orionTenant?: string,
): Promise<RagUploadResult> {
  return new Promise((resolve, reject) => {
    const formData = new FormData()
    formData.append('file', file)
    const params = new URLSearchParams({
      tenant,
      broker_base_url: brokerBaseUrl,
      orion_tenant: orionTenant ?? tenant,
      collection,
    })
    const url = `/api/rag/upload?${params.toString()}`
    const xhr = new XMLHttpRequest()
    xhr.open('POST', url)
    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable && onProgress) onProgress(Math.round((e.loaded / e.total) * 100))
    }
    xhr.onload = () => {
      try {
        resolve(JSON.parse(xhr.responseText) as RagUploadResult)
      } catch {
        resolve({ ok: false, status: xhr.status, filename: file.name, error: xhr.responseText.slice(0, 300) })
      }
    }
    xhr.onerror = () => reject(new Error('Error de red al subir el documento'))
    xhr.send(formData)
  })
}
