import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { getEntities, postEntity, postSubscription, prepareEntityPayload } from '../../api/orion'
import { assertContextReachable } from '../../lib/contextReachability'
import { humanizeSchemaError, validateEntityPayload } from '../../api/validation'
import { buildCreateBasePayload, getSchemaForType } from '../../lib/model-parser'
import { buildQuantumLeapSubscriptionPayload } from '../../lib/subscriptions'
import type { NgsiLdEntity, ValidationResult } from '../../types/entity'

type Props = {
  type: string
  modelJson: string | null
  brokerUrl: string
  brokerTenant?: string
  initialPayload?: Record<string, unknown> | null
  onDirty: () => void
  onCreated: (entity: NgsiLdEntity) => void
  onJsonDraftChange?: (json: string) => void
}

type TemplateSource = 'example' | 'base' | null

function formatJsonSafe(text: string): string {
  try { return JSON.stringify(JSON.parse(text), null, 2) } catch { return text }
}

export function EntityCreate({ type, modelJson, brokerUrl, brokerTenant, initialPayload, onDirty, onCreated, onJsonDraftChange }: Props) {
  const { t } = useTranslation()
  const [json, setJson] = useState('')
  const [templateSource, setTemplateSource] = useState<TemplateSource>(null)
  const [validation, setValidation] = useState<ValidationResult | null>(null)
  const [busy, setBusy] = useState(false)
  const [subscribeToQuantumLeap, setSubscribeToQuantumLeap] = useState(false)
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  function loadTemplate(overridePayload?: Record<string, unknown>) {
    const { payload, fromExample } = buildCreateBasePayload(type, modelJson)
    const base = overridePayload ?? payload
    setJson(JSON.stringify(base, null, 2))
    setTemplateSource(fromExample ? 'example' : 'base')
    setValidation(null)
  }

  useEffect(() => {
    if (initialPayload) {
      setJson(JSON.stringify(initialPayload, null, 2))
      setTemplateSource(null)
    } else {
      loadTemplate()
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [type, initialPayload])

  useEffect(() => {
    if (!onJsonDraftChange || !json) return
    const timer = window.setTimeout(() => onJsonDraftChange(json), 400)
    return () => window.clearTimeout(timer)
  }, [json, onJsonDraftChange])

  function handleFormat() {
    setJson(prev => formatJsonSafe(prev))
    setValidation(null)
  }

  async function handleValidate() {
    let payload: Record<string, unknown>
    try { payload = JSON.parse(json || '{}') as Record<string, unknown> }
    catch (e) { setValidation({ valid: false, errors: [{ path: '', message: t('entities.create.errInvalidJson', { error: String(e) }) }] }); return }
    const schema = getSchemaForType(type, modelJson)
    if (!schema) { setValidation({ valid: false, errors: [{ path: '', message: t('entities.create.errNoSchema', { type }) }] }); return }
    const prep = await prepareEntityPayload(payload, type, null)
    if (prep.error) { setValidation({ valid: false, errors: [{ path: '', message: prep.error }] }); return }
    const vr = await validateEntityPayload(prep.payloadForValidation, schema, prep.inputMode)
    setValidation(vr)
  }

  async function handleCreate() {
    if (!type) return
    let payload: Record<string, unknown>
    try { payload = JSON.parse(json || '{}') as Record<string, unknown> }
    catch (e) { setValidation({ valid: false, errors: [{ path: '', message: t('entities.create.errInvalidJson', { error: String(e) }) }] }); return }

    setBusy(true)
    try {
      try {
        await assertContextReachable(modelJson)
      } catch (e) {
        setValidation({
          valid: false,
          errors: [{ path: '', message: e instanceof Error ? e.message : String(e) }],
        })
        return
      }
      const prep = await prepareEntityPayload(payload, type, null)
      if (prep.error) { setValidation({ valid: false, errors: [{ path: '', message: prep.error }] }); return }
      const { payloadForValidation, payloadToSend, inputMode } = prep
      setJson(JSON.stringify(payloadToSend, null, 2))

      const schema = getSchemaForType(type, modelJson)
      if (schema) {
        const vr = await validateEntityPayload(payloadForValidation, schema, inputMode)
        setValidation(vr)
        if (!vr.valid) return
      }

      const existing = await getEntities(brokerUrl, { id: (payloadToSend.id as string) ?? '', limit: 1, tenant: brokerTenant })
      if (!existing.error && existing.body.length > 0) {
        setValidation({ valid: false, errors: [{ path: '', message: t('entities.create.errDuplicate', { id: payloadToSend.id }) }] })
        return
      }

      const { status, body, error } = await postEntity(brokerUrl, payloadToSend, brokerTenant)
      if (!error && status >= 200 && status < 300) {
        if (subscribeToQuantumLeap) {
          const entityId = payloadToSend.id as string
          const attributes = Object.keys(payloadToSend).filter(
            k => k !== 'id' && k !== 'type' && k !== '@context'
          )
          const subPayload = buildQuantumLeapSubscriptionPayload(entityId, type, attributes)
          const subRes = await postSubscription(brokerUrl, subPayload, brokerTenant)
          if (subRes.error) {
            console.error('Failed to notify quantumleap', subRes.error)
          }
        }
        setValidation({ valid: true, errors: [] })
        onCreated({ id: payloadToSend.id as string, type, ...payloadToSend } as NgsiLdEntity)
      } else {
        const msg = error ?? (body && (body as Record<string, unknown>).title) ?? JSON.stringify(body)
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
      <div className="form-group form-group--grow">
        <label htmlFor="create-json">
          {t('entities.create.payloadLabel')}
          {templateSource && (
            <span className={`template-source ${templateSource === 'example' ? 'ok' : 'muted'}`}>
              {templateSource === 'example' ? t('entities.create.sourceExample') : t('entities.create.sourceBase')}
            </span>
          )}
        </label>
        <textarea
          ref={textareaRef}
          id="create-json"
          className="payload-textarea"
          rows={18}
          placeholder='{"id":"urn:ngsi-ld:Building:001","type":"Building","@context":"..."}'
          value={json}
          onChange={e => { setJson(e.target.value); onDirty() }}
        />
      </div>
      <div className="form-group form-group--static">
        <label style={{ display: 'flex', alignItems: 'center', gap: '8px', cursor: 'pointer' }}>
          <input
            type="checkbox"
            checked={subscribeToQuantumLeap}
            onChange={e => setSubscribeToQuantumLeap(e.target.checked)}
          />
          {t('entities.create.notifyQuantumLeap')}
        </label>
      </div>
      <div className="btn-row">
        <button type="button" className="secondary" onClick={() => loadTemplate()}>
          {t('entities.create.reloadBase')}
        </button>
        <button
          type="button"
          className="secondary"
          title={t('entities.create.formatTitle')}
          onClick={handleFormat}
        >
          {'{ }'}
        </button>
        <button type="button" className="secondary" onClick={handleValidate} disabled={busy}>
          {t('entities.create.validate')}
        </button>
        <button id="btn-create-save" type="button" onClick={handleCreate} disabled={busy}>
          {busy ? t('entities.create.creating') : t('entities.create.create')}
        </button>
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
