import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { EntityEdit } from '../../pages/entities/EntityEdit'
import type { NgsiLdEntity } from '../../types/entity'

// ── Mocks ─────────────────────────────────────────────────────────────────────
vi.mock('../../api/orion', () => ({
  getEntityById:        vi.fn(),
  patchEntityAttrs:     vi.fn(),
  prepareAttrsPayload:  vi.fn(),
}))

vi.mock('../../api/validation', () => ({
  validateAttrsPayload:  vi.fn(),
  humanizeSchemaError:   vi.fn(({ message }: { path: string; message: unknown }) => String(message)),
}))

import { getEntityById, patchEntityAttrs, prepareAttrsPayload } from '../../api/orion'
import { validateAttrsPayload } from '../../api/validation'

const mockGetEntityById       = vi.mocked(getEntityById)
const mockPatchEntityAttrs    = vi.mocked(patchEntityAttrs)

type GetEntityByIdResult = Awaited<ReturnType<typeof getEntityById>>
type PatchEntityResult = Awaited<ReturnType<typeof patchEntityAttrs>>
const mockPrepareAttrsPayload = vi.mocked(prepareAttrsPayload)
const mockValidateAttrsPayload = vi.mocked(validateAttrsPayload)

// ── Formas reales de retorno ──────────────────────────────────────────────────
// getEntityById → { status, error, body: entity | null }
// patchEntityAttrs → { status, error, body: {} }
// prepareAttrsPayload → PrepareAttrsResult = { error, attrsPayloadToSend }
// validateAttrsPayload → ValidationResult = { valid, errors }

function entityOk(entity: NgsiLdEntity) {
  return { status: 200, error: null, body: entity as Record<string, unknown> } as
    ReturnType<typeof getEntityById> extends Promise<infer T> ? T : never
}

function entityError() {
  return { status: 404, error: 'Not found', body: null } as
    ReturnType<typeof getEntityById> extends Promise<infer T> ? T : never
}

function prepareOk() {
  return {
    error: null,
    attrsPayloadToSend: { 'https://schema.org/name': { type: 'Property', value: 'B' } },
  }
}

function validateOk() {
  return { valid: true, errors: [] }
}

function validateFail(msg: string) {
  return { valid: false, errors: [{ path: '', message: msg }] }
}

function patchOk() {
  return { status: 204, error: null, body: {} } as
    ReturnType<typeof patchEntityAttrs> extends Promise<infer T> ? T : never
}

// ── Fixtures ──────────────────────────────────────────────────────────────────
// Usamos tipo único (Sensor) para evitar ambigüedad con el ID

const ENTITY: NgsiLdEntity = {
  id: 'urn:ngsi-ld:Sensor:001',
  type: 'https://example.org/TemperatureSensor',
  name: { value: 'Sensor Planta A' },
  'https://schema.org/temperature': { type: 'Property', value: 22 },
}

const ENTITY_NO_ATTRS: NgsiLdEntity = {
  id: 'urn:ngsi-ld:Sensor:empty',
  type: 'https://example.org/TemperatureSensor',
}

const VALID_ATTRS_JSON = JSON.stringify({
  'https://schema.org/temperature': { type: 'Property', value: 25 },
})

const defaultProps = {
  entity: ENTITY,
  brokerUrl: 'http://localhost:1026',
  onDirty: vi.fn(),
  onSaved: vi.fn(),
  onDelete: vi.fn(),
}

// ── Tests ─────────────────────────────────────────────────────────────────────

describe('EntityEdit', () => {

  beforeEach(() => { vi.clearAllMocks() })

  // ── Render inicial ────────────────────────────────────────────────────────

  it('muestra el ID de la entidad en la barra de información', async () => {
    mockGetEntityById.mockResolvedValue(entityOk(ENTITY))
    render(<EntityEdit {...defaultProps} />)
    await waitFor(() =>
      expect(screen.getByText(/urn:ngsi-ld:Sensor:001/)).toBeInTheDocument()
    )
  })

  it('muestra el tipo de la entidad (al menos parte del nombre)', async () => {
    mockGetEntityById.mockResolvedValue(entityOk(ENTITY))
    render(<EntityEdit {...defaultProps} />)
    await waitFor(() =>
      expect(screen.getAllByText(/TemperatureSensor/i).length).toBeGreaterThan(0)
    )
  })

  it('muestra el botón "Guardar cambios"', async () => {
    mockGetEntityById.mockResolvedValue(entityOk(ENTITY))
    render(<EntityEdit {...defaultProps} />)
    await waitFor(() =>
      expect(screen.getByRole('button', { name: /guardar cambios/i })).toBeInTheDocument()
    )
  })

  it('muestra el botón "Eliminar entidad"', async () => {
    mockGetEntityById.mockResolvedValue(entityOk(ENTITY))
    render(<EntityEdit {...defaultProps} />)
    await waitFor(() =>
      expect(screen.getByRole('button', { name: /eliminar entidad/i })).toBeInTheDocument()
    )
  })

  it('muestra el botón "Validar"', async () => {
    mockGetEntityById.mockResolvedValue(entityOk(ENTITY))
    render(<EntityEdit {...defaultProps} />)
    await waitFor(() =>
      expect(screen.getByRole('button', { name: /validar/i })).toBeInTheDocument()
    )
  })

  it('el textarea está en readonly durante la carga', () => {
    let resolveGet!: (v: GetEntityByIdResult) => void
    mockGetEntityById.mockImplementation(() => new Promise((r) => { resolveGet = r }))
    render(<EntityEdit {...defaultProps} />)
    expect(screen.getByRole('textbox')).toHaveAttribute('readonly')
    resolveGet(entityOk(ENTITY))
  })

  it('el textarea deja de estar en readonly tras la carga', async () => {
    mockGetEntityById.mockResolvedValue(entityOk(ENTITY))
    render(<EntityEdit {...defaultProps} />)
    await waitFor(() =>
      expect(screen.getByRole('textbox')).not.toHaveAttribute('readonly')
    )
  })

  // ── Error de carga ────────────────────────────────────────────────────────

  it('muestra error cuando getEntityById devuelve error', async () => {
    mockGetEntityById.mockResolvedValue(entityError())
    render(<EntityEdit {...defaultProps} />)
    await waitFor(() =>
      expect(screen.getByText(/error cargando/i)).toBeInTheDocument()
    )
  })

  it('muestra error cuando getEntityById devuelve error de red (status 0)', async () => {
    // La función real nunca rechaza — devuelve { status: 0, error: '...', body: null }
    mockGetEntityById.mockResolvedValue({ status: 0, error: 'Sin conexión', body: null } as
      ReturnType<typeof getEntityById> extends Promise<infer T> ? T : never)
    render(<EntityEdit {...defaultProps} />)
    await waitFor(() =>
      expect(screen.getByText(/error cargando/i)).toBeInTheDocument()
    )
  })

  // ── Entidad sin atributos ─────────────────────────────────────────────────

  it('muestra aviso cuando la entidad no tiene atributos', async () => {
    mockGetEntityById.mockResolvedValue(entityOk(ENTITY_NO_ATTRS))
    render(<EntityEdit {...defaultProps} entity={ENTITY_NO_ATTRS} />)
    await waitFor(() =>
      expect(screen.getByText(/no tiene atributos/i)).toBeInTheDocument()
    )
  })

  // ── Guardar cambios ───────────────────────────────────────────────────────

  it('llama onSaved tras guardar correctamente', async () => {
    const onSaved = vi.fn()
    mockGetEntityById.mockResolvedValue(entityOk(ENTITY))
    mockPrepareAttrsPayload.mockResolvedValue(prepareOk())
    mockValidateAttrsPayload.mockResolvedValue(validateOk())
    mockPatchEntityAttrs.mockResolvedValue(patchOk())
    render(<EntityEdit {...defaultProps} onSaved={onSaved} />)
    await waitFor(() => expect(screen.getByRole('textbox')).not.toHaveAttribute('readonly'))
    fireEvent.change(screen.getByRole('textbox'), { target: { value: VALID_ATTRS_JSON } })
    fireEvent.click(screen.getByRole('button', { name: /guardar cambios/i }))
    await waitFor(() => expect(onSaved).toHaveBeenCalledTimes(1), { timeout: 5000 })
  })

  it('no llama patchEntityAttrs si la validación devuelve errores', async () => {
    mockGetEntityById.mockResolvedValue(entityOk(ENTITY))
    mockPrepareAttrsPayload.mockResolvedValue(prepareOk())
    mockValidateAttrsPayload.mockResolvedValue(validateFail('campo inválido'))
    render(<EntityEdit {...defaultProps} />)
    await waitFor(() => expect(screen.getByRole('textbox')).not.toHaveAttribute('readonly'))
    fireEvent.change(screen.getByRole('textbox'), { target: { value: VALID_ATTRS_JSON } })
    fireEvent.click(screen.getByRole('button', { name: /guardar cambios/i }))
    await waitFor(() => expect(mockPrepareAttrsPayload).toHaveBeenCalled())
    expect(mockPatchEntityAttrs).not.toHaveBeenCalled()
  })

  // ── Eliminar entidad ──────────────────────────────────────────────────────
  // EntityEdit llama onDelete() directamente — el modal de confirmación
  // lo gestiona el componente padre (EntitiesPage).

  it('llama onDelete al hacer clic en "Eliminar entidad"', async () => {
    const onDelete = vi.fn()
    mockGetEntityById.mockResolvedValue(entityOk(ENTITY))
    render(<EntityEdit {...defaultProps} onDelete={onDelete} />)
    await waitFor(() =>
      expect(screen.getByRole('button', { name: /eliminar entidad/i })).toBeInTheDocument()
    )
    fireEvent.click(screen.getByRole('button', { name: /eliminar entidad/i }))
    expect(onDelete).toHaveBeenCalledTimes(1)
  })

  it('el botón "Eliminar entidad" está deshabilitado durante el guardado', async () => {
    let resolvePatch!: (v: PatchEntityResult) => void
    mockGetEntityById.mockResolvedValue(entityOk(ENTITY))
    mockPrepareAttrsPayload.mockResolvedValue(prepareOk())
    mockValidateAttrsPayload.mockResolvedValue(validateOk())
    mockPatchEntityAttrs.mockImplementation(() => new Promise((r) => { resolvePatch = r }))
    render(<EntityEdit {...defaultProps} />)
    await waitFor(() => expect(screen.getByRole('textbox')).not.toHaveAttribute('readonly'))
    fireEvent.change(screen.getByRole('textbox'), { target: { value: VALID_ATTRS_JSON } })
    fireEvent.click(screen.getByRole('button', { name: /guardar cambios/i }))
    await waitFor(() =>
      expect(screen.getByRole('button', { name: /eliminar entidad/i })).toBeDisabled()
    )
    resolvePatch(patchOk())
  })

  // ── Edición sucia ─────────────────────────────────────────────────────────

  it('llama onDirty al editar el textarea', async () => {
    const onDirty = vi.fn()
    mockGetEntityById.mockResolvedValue(entityOk(ENTITY))
    render(<EntityEdit {...defaultProps} onDirty={onDirty} />)
    await waitFor(() => expect(screen.getByRole('textbox')).not.toHaveAttribute('readonly'))
    fireEvent.change(screen.getByRole('textbox'), { target: { value: VALID_ATTRS_JSON } })
    expect(onDirty).toHaveBeenCalled()
  })

  // ── Formatear JSON ────────────────────────────────────────────────────────

  it('el botón de formatear no rompe si el JSON es inválido', async () => {
    mockGetEntityById.mockResolvedValue(entityOk(ENTITY))
    render(<EntityEdit {...defaultProps} />)
    await waitFor(() => expect(screen.getByRole('textbox')).not.toHaveAttribute('readonly'))
    fireEvent.change(screen.getByRole('textbox'), { target: { value: '{ json roto }' } })
    expect(() => fireEvent.click(screen.getByTitle(/formatear json/i))).not.toThrow()
  })

})
