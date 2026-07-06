/** Misma regla que rag-manager `POST /tenants`: minúsculas y espacios → _. */
export function normalizeRagTenantId(raw: string): string {
  return raw.trim().toLowerCase().replace(/\s+/g, '_')
}
