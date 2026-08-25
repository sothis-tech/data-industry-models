import i18n from '../lib/i18n'
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
      return { valid: false, errors: [{ path: '', message: detailToString(data.detail, i18n.t('errors.validation.failed')) }] }
    }
    return data
  } catch (e) {
    return { valid: false, errors: [{ path: '', message: i18n.t('errors.validation.noConnection', { error: String(e) }) }] }
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
      return { valid: false, errors: [{ path: '', message: detailToString(data.detail, i18n.t('errors.validation.failed')) }] }
    }
    return data
  } catch (e) {
    return { valid: false, errors: [{ path: '', message: i18n.t('errors.validation.noConnection', { error: String(e) }) }] }
  }
}
export function humanizeSchemaError({ path, message }: { path: string; message: unknown }): string {
  // `message` puede llegar como objeto en runtime aunque el tipo diga string
  const msg = typeof message === 'string' ? message : JSON.stringify(message)
  const field = path && path !== '/' ? i18n.t('errors.schema.fieldNamed', { field: path.replace(/^\//, '') }) : i18n.t('errors.schema.payload')
  if (/is not one of/i.test(msg)) {
    const got = (msg.match(/'([^']+)' is not/) ?? [])[1] ?? ''
    const allowed = (msg.match(/\[([^\]]+)\]/) ?? [])[1] ?? ''
    if (path === '/type') {
      const expected = (msg.match(/\['([^\]]+)'\]/) ?? [])[1] ?? ''
      return i18n.t('errors.schema.typeNotValid', { field, got, expected })
    }
    const hint =
      path.replace(/^\//, '').startsWith('category') && got
        ? i18n.t('errors.schema.categoryHint', { got })
        : ''
    const allowedText = allowed
      ? i18n.t('errors.schema.allowedValues', { allowed: allowed.length > 120 ? `${allowed.slice(0, 120)}…` : allowed })
      : ''
    return i18n.t('errors.schema.valueNotAllowed', { field, got, hint, allowedText })
  }
  if (/is a required property/i.test(msg)) {
    const prop = (msg.match(/'([^']+)' is a required/) ?? [])[1] ?? ''
    return i18n.t('errors.schema.requiredMissing', { prop })
  }
  if (/is not of type/i.test(msg)) {
    const expected = (msg.match(/of type '([^']+)'/) ?? [])[1] ?? ''
    return i18n.t('errors.schema.wrongType', { field, expected })
  }
  if (/is not valid under any of the given schemas/i.test(msg)) {
    return i18n.t('errors.schema.invalidStructure', { field })
  }
  return i18n.t('errors.schema.generic', { field, msg })
}
