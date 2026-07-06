import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { EntityCreate } from '../../pages/entities/EntityCreate'

// ── Mocks ─────────────────────────────────────────────────────────────────────
vi.mock('../../api/orion', () => ({
  getEntities:          vi.fn(),
  postEntity:           vi.fn(),
  prepareEntityPayload: vi.fn(),
  postSubscription:     vi.fn(),
}))

vi.mock('../../api/validation', () => ({
  validateEntityPayload: vi.fn(),
  humanizeSchemaError:   vi.fn(({ message }: { path: string; message: unknown }) => String(message)),
}))

import { getEntities, postEntity, prepareEntityPayload, postSubscription } from '../../api/orion'
import { validateEntityPayload } from '../../api/validation'

const mockGetEntities          = vi.mocked(getEntities)
const mockPostEntity           = vi.mocked(postEntity)
const mockPrepareEntityPayload = vi.mocked(prepareEntityPayload)
const mockValidateEntityPayload = vi.mocked(validateEntityPayload)
const mockPostSubscription      = vi.mocked(postSubscription)

// ── Formas reales de retorno ──────────────────────────────────────────────────
// prepareEntityPayload → PreparePayloadResult
// validateEntityPayload → ValidationResult
// getEntities → ApiResult<{body:[]}> = { status, error, body }
// postEntity → ApiResult<{body:{}}> = { status, error, body }

function preparePaylResult(overrides?: Partial<{error: null|string}>) {
  return {
    error:                overrides?.error ?? null,
    inputMode:            'plain' as const,
    payloadForValidation: { id: 'urn:ngsi-ld:Machine:001', type: 'Machine', Presion: 10, Temperatura: 20 },
    payloadToSend:        { id: 'urn:ngsi-ld:Machine:001', type: 'Machine', Presion: 10, Temperatura: 20 },
  }
}

function validOk() {
  return { valid: true,  errors: [] }
}

function validFail(msg: string) {
  return { valid: false, errors: [{ path: '', message: msg }] }
}

function getEntitiesEmpty() {
  return { status: 200, error: null, body: [] } as ReturnType<typeof getEntities> extends Promise<infer T> ? T : never
}

function getEntitiesWithOne() {
  return {
    status: 200, error: null,
    body: [{ id: 'urn:ngsi-ld:Machine:001', type: 'Machine' }],
  } as ReturnType<typeof getEntities> extends Promise<infer T> ? T : never
}

function postOk() {
  return { status: 201, error: null, body: { id: 'urn:ngsi-ld:Machine:001', type: 'Machine' } } as
    ReturnType<typeof postEntity> extends Promise<infer T> ? T : never
}

function postSubscriptionOk() {
  return { status: 201, error: null, body: {} } as
    ReturnType<typeof postSubscription> extends Promise<infer T> ? T : never
}

// ── Fixtures ──────────────────────────────────────────────────────────────────

const BROKER = 'http://localhost:1026'

const MODEL_JSON = JSON.stringify({
  schemas: [{
    $schema: 'https://json-schema.org/draft/2020-12/schema',
    title: 'Machine', type: 'object',
    required: ['id', 'type'],
    properties: { id: { type: 'string' }, type: { type: 'string' }, name: { type: 'string' } },
  }],
  context: { '@context': { Machine: 'https://example.org/Machine' } },
  descriptor: null,
  examples: {},
})

const VALID_ENTITY_JSON = JSON.stringify({
  id: 'urn:ngsi-ld:Machine:001',
  type: 'Machine',
  '@context': 'https://example.org/ctx',
})

const defaultProps = {
  type: 'Machine',
  modelJson: MODEL_JSON,
  brokerUrl: BROKER,
  initialPayload: null,
  onDirty: vi.fn(),
  onCreated: vi.fn(),
}

// ── Tests ─────────────────────────────────────────────────────────────────────

describe('EntityCreate', () => {

  beforeEach(() => {
    vi.clearAllMocks()
    mockGetEntities.mockResolvedValue(getEntitiesEmpty())
  })

  // ── Render ───────────────────────────────────────────────────────────────

  it('muestra el textarea de payload', () => {
    render(<EntityCreate {...defaultProps} />)
    expect(screen.getByRole('textbox')).toBeInTheDocument()
  })

  it('muestra el botón "Crear entidad"', () => {
    render(<EntityCreate {...defaultProps} />)
    expect(screen.getByRole('button', { name: /crear entidad/i })).toBeInTheDocument()
  })

  it('muestra el botón "Validar"', () => {
    render(<EntityCreate {...defaultProps} />)
    expect(screen.getByRole('button', { name: /validar/i })).toBeInTheDocument()
  })

  it('muestra el botón de formatear JSON', () => {
    render(<EntityCreate {...defaultProps} />)
    expect(screen.getByTitle(/formatear json/i)).toBeInTheDocument()
  })

  it('muestra el botón "Recargar base"', () => {
    render(<EntityCreate {...defaultProps} />)
    expect(screen.getByRole('button', { name: /recargar/i })).toBeInTheDocument()
  })

  // ── Payload inicial ───────────────────────────────────────────────────────

  it('usa initialPayload cuando se proporciona', () => {
    const payload = { id: 'urn:ngsi-ld:Machine:999', type: 'Machine', '@context': 'x' }
    render(<EntityCreate {...defaultProps} initialPayload={payload} />)
    const textarea = screen.getByRole('textbox') as HTMLTextAreaElement
    expect(textarea.value).toContain('urn:ngsi-ld:Machine:999')
  })

  // ── Edición del JSON ──────────────────────────────────────────────────────

  it('llama onDirty al editar el textarea', () => {
    const onDirty = vi.fn()
    render(<EntityCreate {...defaultProps} onDirty={onDirty} />)
    fireEvent.change(screen.getByRole('textbox'), { target: { value: '{"id":"x"}' } })
    expect(onDirty).toHaveBeenCalled()
  })

  it('formatea el JSON al hacer clic en el botón de formatear', () => {
    render(<EntityCreate {...defaultProps} />)
    const textarea = screen.getByRole('textbox') as HTMLTextAreaElement
    fireEvent.change(textarea, { target: { value: '{"id":"x","type":"Machine"}' } })
    fireEvent.click(screen.getByTitle(/formatear json/i))
    expect(textarea.value).toContain('\n')
  })

  it('el botón de formatear no rompe si el JSON es inválido', () => {
    render(<EntityCreate {...defaultProps} />)
    const textarea = screen.getByRole('textbox')
    fireEvent.change(textarea, { target: { value: '{ json invalido }' } })
    expect(() => fireEvent.click(screen.getByTitle(/formatear json/i))).not.toThrow()
  })

  // ── Validación ────────────────────────────────────────────────────────────

  it('muestra resultado positivo en el pre de validación tras validación exitosa', async () => {
    mockPrepareEntityPayload.mockResolvedValue(preparePaylResult())
    mockValidateEntityPayload.mockResolvedValue(validOk())
    render(<EntityCreate {...defaultProps} />)
    fireEvent.change(screen.getByRole('textbox'), { target: { value: VALID_ENTITY_JSON } })
    fireEvent.click(screen.getByRole('button', { name: /validar/i }))
    await waitFor(() => {
      const pre = document.querySelector('pre.validation-output')
      expect(pre).toBeInTheDocument()
      expect(pre?.className).not.toMatch(/error/)
    })
  })

  it('el pre de validación tiene clase error cuando el JSON es inválido', async () => {
    render(<EntityCreate {...defaultProps} />)
    fireEvent.change(screen.getByRole('textbox'), { target: { value: '{ json roto }' } })
    fireEvent.click(screen.getByRole('button', { name: /validar/i }))
    await waitFor(() => {
      const pre = document.querySelector('pre.validation-output')
      expect(pre).toBeInTheDocument()
      expect(pre?.className).toMatch(/error/)
    })
  })

  it('muestra error humanizado cuando la validación devuelve errores', async () => {
    mockPrepareEntityPayload.mockResolvedValue(preparePaylResult())
    mockValidateEntityPayload.mockResolvedValue(validFail('campo requerido faltante'))
    render(<EntityCreate {...defaultProps} />)
    fireEvent.change(screen.getByRole('textbox'), { target: { value: VALID_ENTITY_JSON } })
    fireEvent.click(screen.getByRole('button', { name: /validar/i }))
    await waitFor(() =>
      expect(screen.getByText(/campo requerido/i)).toBeInTheDocument()
    )
  })

  // ── Creación exitosa ───────────────────────────────────────────────────────

  it('llama onCreated tras crear la entidad correctamente', async () => {
    const onCreated = vi.fn()
    mockPrepareEntityPayload.mockResolvedValue(preparePaylResult())
    mockValidateEntityPayload.mockResolvedValue(validOk())
    mockPostEntity.mockResolvedValue(postOk())
    render(<EntityCreate {...defaultProps} onCreated={onCreated} />)
    fireEvent.change(screen.getByRole('textbox'), { target: { value: VALID_ENTITY_JSON } })
    fireEvent.click(screen.getByRole('button', { name: /crear entidad/i }))
    await waitFor(() => expect(onCreated).toHaveBeenCalled(), { timeout: 5000 })
  })

  // ── No crea si validación falla ────────────────────────────────────────────

  it('no llama postEntity si la validación devuelve errores', async () => {
    mockPrepareEntityPayload.mockResolvedValue(preparePaylResult())
    mockValidateEntityPayload.mockResolvedValue(validFail('campo requerido'))
    render(<EntityCreate {...defaultProps} />)
    fireEvent.change(screen.getByRole('textbox'), { target: { value: VALID_ENTITY_JSON } })
    fireEvent.click(screen.getByRole('button', { name: /crear entidad/i }))
    await waitFor(() => expect(mockPrepareEntityPayload).toHaveBeenCalled())
    expect(mockPostEntity).not.toHaveBeenCalled()
  })

  it('no llama postEntity si hay error en prepareEntityPayload', async () => {
    mockPrepareEntityPayload.mockResolvedValue(preparePaylResult({ error: 'Sin conexión' }))
    render(<EntityCreate {...defaultProps} />)
    fireEvent.change(screen.getByRole('textbox'), { target: { value: VALID_ENTITY_JSON } })
    fireEvent.click(screen.getByRole('button', { name: /crear entidad/i }))
    await waitFor(() => expect(mockPrepareEntityPayload).toHaveBeenCalled())
    expect(mockPostEntity).not.toHaveBeenCalled()
  })

  // ── Duplicado de ID ───────────────────────────────────────────────────────

  it('no llama postEntity cuando ya existe la entidad con ese ID', async () => {
    mockGetEntities.mockResolvedValue(getEntitiesWithOne())
    mockPrepareEntityPayload.mockResolvedValue(preparePaylResult())
    mockValidateEntityPayload.mockResolvedValue(validOk())
    render(<EntityCreate {...defaultProps} />)
    fireEvent.change(screen.getByRole('textbox'), { target: { value: VALID_ENTITY_JSON } })
    fireEvent.click(screen.getByRole('button', { name: /crear entidad/i }))
    await waitFor(() => expect(mockPrepareEntityPayload).toHaveBeenCalled())
    await waitFor(() => expect(mockGetEntities).toHaveBeenCalled())
    expect(mockPostEntity).not.toHaveBeenCalled()
  })

  // ── Notificación QuantumLeap ───────────────────────────────────────────────

  it('no llama postSubscription cuando el checkbox no está marcado y la creación es exitosa', async () => {
    const onCreated = vi.fn()
    mockPrepareEntityPayload.mockResolvedValue(preparePaylResult())
    mockValidateEntityPayload.mockResolvedValue(validOk())
    mockPostEntity.mockResolvedValue(postOk())
    render(<EntityCreate {...defaultProps} onCreated={onCreated} />)
    
    fireEvent.change(screen.getByRole('textbox'), { target: { value: VALID_ENTITY_JSON } })
    fireEvent.click(screen.getByRole('button', { name: /crear entidad/i }))
    
    await waitFor(() => expect(onCreated).toHaveBeenCalled(), { timeout: 5000 })
    expect(mockPostSubscription).not.toHaveBeenCalled()
  })

  it('llama postSubscription cuando el checkbox está marcado y la creación es exitosa', async () => {
    const onCreated = vi.fn()
    mockPrepareEntityPayload.mockResolvedValue(preparePaylResult())
    mockValidateEntityPayload.mockResolvedValue(validOk())
    mockPostEntity.mockResolvedValue(postOk())
    mockPostSubscription.mockResolvedValue(postSubscriptionOk())

    render(<EntityCreate {...defaultProps} onCreated={onCreated} />)
    
    // Marcar el checkbox
    fireEvent.click(screen.getByLabelText(/notificar a quantumleap/i))

    fireEvent.change(screen.getByRole('textbox'), { target: { value: VALID_ENTITY_JSON } })
    fireEvent.click(screen.getByRole('button', { name: /crear entidad/i }))

    await waitFor(() => expect(onCreated).toHaveBeenCalled(), { timeout: 5000 })
    expect(mockPostSubscription).toHaveBeenCalledWith(
      BROKER,
      {
        description: 'Suscripción para persistir atributos de Machine',
        type: 'Subscription',
        entities: [
          {
            id: 'urn:ngsi-ld:Machine:001',
            type: 'Machine'
          }
        ],
        watchedAttributes: ['Presion', 'Temperatura'],
        notification: {
          attributes: ['Presion', 'Temperatura'],
          format: 'normalized',
          endpoint: {
            uri: 'http://quantumleap:8668/v2/notify',
            accept: 'application/json'
          }
        },
        '@context': [
          'https://uri.etsi.org/ngsi-ld/v1/ngsi-ld-core-context.jsonld'
        ]
      },
      undefined
    )
  })
})
