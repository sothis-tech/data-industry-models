import type { ValidationResult } from '../types/entity'

/** Extrae un mensaje legible del campo `detail` que Pydantic puede devolver como string o array */
function detailToString(detail: unknown, fallback: string): string {
  if (!detail) return fallback
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) {
    return detail
      .map((d: unknown) => {
        if (d && typeof d === 'object' && 'msg' in (d as object)) return String((d as { msg: unknown }).msg)
        return String(d)
      })
      .join('; ')
  }
  return fallback
}

export async function validateEntityPayload(
  payload: unknown,
  schemaDoc: unknown,
  payloadMode: string = 'auto',
): Promise<ValidationResult> {
  try {
    const res = await fetch('/api/validate/entity', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ payload, schema_doc: schemaDoc, payload_mode: payloadMode }),
    })
    const data = await res.json().catch(() => ({})) as ValidationResult & { detail?: unknown }
    if (!res.ok) {
      return { valid: false, errors: [{ path: '', message: detailToString(data.detail, 'Error de validación') }] }
    }
    return data
  } catch (e) {
    return { valid: false, errors: [{ path: '', message: 'Sin conexión: ' + String(e) }] }
  }
}

export async function validateAttrsPayload(attrsPayload: unknown): Promise<ValidationResult> {
  try {
    const res = await fetch('/api/validate/attrs', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ attrs_payload: attrsPayload }),
    })
    const data = await res.json().catch(() => ({})) as ValidationResult & { detail?: unknown }
    if (!res.ok) {
      return { valid: false, errors: [{ path: '', message: detailToString(data.detail, 'Error de validación') }] }
    }
    return data
  } catch (e) {
    return { valid: false, errors: [{ path: '', message: 'Sin conexión: ' + String(e) }] }
  }
}

export function humanizeSchemaError({ path, message }: { path: string; message: unknown }): string {
  // `message` puede llegar como objeto en runtime aunque el tipo diga string
  const msg = typeof message === 'string' ? message : JSON.stringify(message)
  const field = path && path !== '/' ? `Campo "${path.replace(/^\//, '')}"` : 'Payload'

  if (/is not one of/i.test(msg)) {
    const got = (msg.match(/'([^']+)' is not/) ?? [])[1] ?? ''
    const allowed = (msg.match(/\[([^\]]+)\]/) ?? [])[1] ?? ''
    if (path === '/type') {
      const expected = (msg.match(/\['([^\]]+)'\]/) ?? [])[1] ?? ''
      return `${field}: el tipo '${got}' no es válido para este schema (se esperaba '${expected}'). Revisa que el tipo seleccionado coincide con el payload.`
    }
    const hint =
      path.replace(/^\//, '').startsWith('category') && got
        ? ` El valor '${got}' no pertenece al enum de categorías de edificio (Building); a veces Marvin mezcla categorías de Device (p. ej. manufacturingPlant).`
        : ''
    return `${field}: el valor '${got}' no está permitido por el schema.${hint}${allowed ? ` Valores válidos (extracto): [${allowed.length > 120 ? `${allowed.slice(0, 120)}…` : allowed}].` : ''}`
  }
  if (/is a required property/i.test(msg)) {
    const prop = (msg.match(/'([^']+)' is a required/) ?? [])[1] ?? ''
    return `Campo requerido faltante: "${prop}". Añádelo al JSON antes de crear.`
  }
  if (/is not of type/i.test(msg)) {
    const expected = (msg.match(/of type '([^']+)'/) ?? [])[1] ?? ''
    return `${field}: se esperaba un valor de tipo ${expected}.`
  }
  if (/is not valid under any of the given schemas/i.test(msg)) {
    return `${field}: la estructura del valor no es válida según el schema. Comprueba que el formato (p. ej. GeoJSON para location) es correcto.`
  }
  return `${field}: ${msg}`
}
