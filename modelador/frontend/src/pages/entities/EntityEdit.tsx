import { useEffect, useState } from 'react'
import { useTranslation, Trans } from 'react-i18next'
import { getEntityById, patchEntityAttrs, prepareAttrsPayload } from '../../api/orion'
import { humanizeSchemaError, validateAttrsPayload } from '../../api/validation'
import type { NgsiLdEntity, ValidationResult } from '../../types/entity'

type Props = {
  entity: NgsiLdEntity
  brokerUrl: string
  brokerTenant?: string
  onDirty: () => void
  onSaved: () => void
  onDelete: () => void
  onJsonDraftChange?: (json: string) => void
}

function formatJsonSafe(text: string): string {
  try { return JSON.stringify(JSON.parse(text), null, 2) } catch { return text }
}

export function EntityEdit({ entity, brokerUrl, brokerTenant, onDirty, onSaved, onDelete, onJsonDraftChange }: Props) {
  const { t } = useTranslation()
  const [json, setJson] = useState('')
  const [infoHtml, setInfoHtml] = useState<{ id: string; type: string; noAttrs: boolean } | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [validation, setValidation] = useState<ValidationResult | null>(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    setJson('')
    setValidation(null)
    setLoadError(null)
    setInfoHtml(null)

    async function load() {
      setLoading(true)
      const { body, error } = await getEntityById(brokerUrl, entity.id, brokerTenant)
      setLoading(false)
      if (error || !body) {
        setLoadError(error ?? t('entities.edit.emptyResponse'))
        return
      }
      const attrs: Record<string, unknown> = {}
      for (const [k, v] of Object.entries(body)) {
        if (k === 'id' || k === 'type' || k === '@context') continue
        attrs[k] = v
      }
      setJson(JSON.stringify(attrs, null, 2))
      const realType = (String(body.type ?? '').split('/').pop()) || '—'
      setInfoHtml({ id: body.id as string ?? entity.id, type: realType, noAttrs: Object.keys(attrs).length === 0 })
    }
    void load()
  }, [entity.id, brokerUrl])

  useEffect(() => {
    if (!onJsonDraftChange || loading || !json) return
    const timer = window.setTimeout(() => onJsonDraftChange(json), 400)
    return () => window.clearTimeout(timer)
  }, [json, loading, onJsonDraftChange])

  function handleFormat() {
    setJson(prev => formatJsonSafe(prev))
    setValidation(null)
  }

  async function handleValidate() {
    let payload: Record<string, unknown>
    try { payload = JSON.parse(json || '{}') as Record<string, unknown> }
    catch (e) { setValidation({ valid: false, errors: [{ path: '', message: t('entities.create.errInvalidJson', { error: String(e) }) }] }); return }
    const prep = await prepareAttrsPayload(payload)
    if (prep.error) { setValidation({ valid: false, errors: [{ path: '', message: prep.error }] }); return }
    setJson(JSON.stringify(prep.attrsPayloadToSend, null, 2))
    const vr = await validateAttrsPayload(prep.attrsPayloadToSend)
    setValidation(vr)
  }

  async function handleSave() {
    let payload: Record<string, unknown>
    try { payload = JSON.parse(json || '{}') as Record<string, unknown> }
    catch (e) { setValidation({ valid: false, errors: [{ path: '', message: t('entities.create.errInvalidJson', { error: String(e) }) }] }); return }

    setBusy(true)
    try {
      const prep = await prepareAttrsPayload(payload)
      if (prep.error) { setValidation({ valid: false, errors: [{ path: '', message: prep.error }] }); return }
      const payloadToSend = prep.attrsPayloadToSend
      setJson(JSON.stringify(payloadToSend, null, 2))

      const vr = await validateAttrsPayload(payloadToSend)
      setValidation(vr)
      if (!vr.valid) return

      const { status, body, error } = await patchEntityAttrs(brokerUrl, entity.id, payloadToSend, brokerTenant)
      if (!error && status >= 200 && status < 300) {
        setValidation({ valid: true, errors: [] })
        onSaved()
      } else {
        const b = body as Record<string, unknown>
        const msg = error ?? (b?.title as string) ?? JSON.stringify(body)
        setValidation({ valid: false, errors: [{ path: '', message: t('entities.create.errCreate', { status: String(status), msg: String(msg) }) }] })
      }
    } finally {
      setBusy(false)
    }
  }

  const validationText = validation
    ? validation.valid
      ? t('entities.create.validationOk')
      : validation.errors.map(humanizeSchemaError).join('\n')
    : ''

  return (
    <div className="detail-body">
      {loadError && (
        <div className="entity-load-error">
          ⚠ {t('entities.edit.loadError', { error: loadError })}
        </div>
      )}
      {infoHtml && (
        <div className="entity-info-bar">
          <span><code>{infoHtml.id}</code> · {t('entities.edit.typeLabel')}: <code className="accent">{infoHtml.type}</code></span>
          {infoHtml.noAttrs && (
            <span className="entity-no-attrs">
              ⚠ <Trans i18nKey="entities.edit.noAttrs" components={{ strong: <strong /> }} />
            </span>
          )}
        </div>
      )}
      <div className="form-group form-group--grow">
        <label htmlFor="patch-json">{t('entities.edit.attrsLabel')}</label>
        <textarea
          id="patch-json"
          className="payload-textarea"
          rows={16}
          placeholder={loading ? t('entities.edit.loadingAttrs') : '{"name":{"type":"Property","value":"nuevo valor"}}'}
          value={json}
          onChange={e => { setJson(e.target.value); onDirty() }}
          readOnly={loading}
        />
      </div>
      <div className="btn-row btn-row--space-between">
        <button type="button" className="secondary danger" onClick={onDelete} disabled={busy}>
          {t('entities.edit.deleteEntity')}
        </button>
        <span className="btn-group">
          <button
            type="button"
            className="secondary"
            title={t('entities.create.formatTitle')}
            onClick={handleFormat}
            disabled={busy}
          >
            {'{ }'}
          </button>
          <button type="button" className="secondary" onClick={handleValidate} disabled={busy || loading}>
            {t('entities.create.validate')}
          </button>
          <button id="btn-patch-save" type="button" onClick={handleSave} disabled={busy || loading}>
            {busy ? t('entities.edit.saving') : t('entities.edit.saveChanges')}
          </button>
        </span>
      </div>
      {validation && (
        <pre className={`validation-output ${validation.valid ? 'ok' : 'error'}`}>
          {validationText}
        </pre>
      )}
      {!validation && <pre className="validation-output placeholder"> </pre>}
    </div>
  )
}
