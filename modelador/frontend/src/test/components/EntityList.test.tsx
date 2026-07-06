import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { EntityList } from '../../pages/entities/EntityList'
import type { NgsiLdEntity } from '../../types/entity'

// ── Fixtures ──────────────────────────────────────────────────────────────────
// NgsiLdEntity.name es { value?: string } | string — entityLabel muestra name.value,
// name (string), o entity.id si no hay nombre.

const ENTITY_MACHINE: NgsiLdEntity = {
  id: 'urn:ngsi-ld:Machine:001',
  type: 'https://example.org/Machine',
  name: { value: 'Horno A' },
}

const ENTITY_AREA: NgsiLdEntity = {
  id: 'urn:ngsi-ld:Area:001',
  type: 'https://example.org/Area',
  // Sin name → entityLabel devuelve el id
}

const ENTITIES = [ENTITY_MACHINE, ENTITY_AREA]

const defaultProps = {
  entities: ENTITIES,
  allCount: 2,
  types: ['Machine', 'Area'],
  typeFilter: '',
  search: '',
  loading: false,
  loadCount: null,
  selectedId: null,
  onTypeFilterChange: vi.fn(),
  onSearchChange: vi.fn(),
  onSelect: vi.fn(),
  onNewEntity: vi.fn(),
}

// ── Helpers ───────────────────────────────────────────────────────────────────
// El input es type="search" → rol ARIA "searchbox"
function getSearchInput() {
  return screen.getByRole('searchbox', { name: /buscar entidades/i })
}

describe('EntityList', () => {

  // ── Render básico ─────────────────────────────────────────────────────────

  it('muestra el botón "+ Nueva entidad"', () => {
    render(<EntityList {...defaultProps} />)
    expect(screen.getByRole('button', { name: /nueva entidad/i })).toBeInTheDocument()
  })

  it('muestra el campo de búsqueda', () => {
    render(<EntityList {...defaultProps} />)
    expect(getSearchInput()).toBeInTheDocument()
  })

  it('muestra la entidad con nombre (name.value)', () => {
    render(<EntityList {...defaultProps} />)
    expect(screen.getByText('Horno A')).toBeInTheDocument()
  })

  it('muestra la entidad sin nombre como su ID', () => {
    render(<EntityList {...defaultProps} />)
    expect(screen.getByText('urn:ngsi-ld:Area:001')).toBeInTheDocument()
  })

  it('muestra el contador total de entidades', () => {
    render(<EntityList {...defaultProps} />)
    expect(screen.getByText(/2/)).toBeInTheDocument()
  })

  // ── Estado loading ────────────────────────────────────────────────────────

  it('muestra "Cargando…" cuando loading es true', () => {
    render(<EntityList {...defaultProps} entities={[]} allCount={0} loading={true} />)
    expect(screen.getByText(/cargando/i)).toBeInTheDocument()
  })

  it('no muestra entidades mientras está cargando', () => {
    render(<EntityList {...defaultProps} entities={[]} allCount={0} loading={true} />)
    expect(screen.queryByText('Horno A')).not.toBeInTheDocument()
  })

  // ── Lista vacía ───────────────────────────────────────────────────────────

  it('muestra mensaje cuando lista está vacía sin búsqueda ni filtro', () => {
    render(<EntityList {...defaultProps} entities={[]} allCount={0} />)
    // El componente muestra un mensaje de lista vacía
    expect(screen.getByText(/no hay|sin entidades|vacío|entidades/i)).toBeInTheDocument()
  })

  it('muestra mensaje distinto cuando hay búsqueda activa y lista vacía', () => {
    render(<EntityList {...defaultProps} entities={[]} allCount={5} search="xyzabc" />)
    // Con búsqueda activa el mensaje menciona la búsqueda o la ausencia de resultados
    expect(
      screen.getByText(/sin resultados|no se encontr|no coincide|xyzabc/i)
    ).toBeInTheDocument()
  })

  // ── Selección ─────────────────────────────────────────────────────────────

  it('llama onSelect al hacer clic en la entidad con nombre', () => {
    const onSelect = vi.fn()
    render(<EntityList {...defaultProps} onSelect={onSelect} />)
    fireEvent.click(screen.getByText('Horno A'))
    expect(onSelect).toHaveBeenCalled()
  })

  it('marca la entidad seleccionada con clase active', () => {
    render(<EntityList {...defaultProps} selectedId={ENTITY_MACHINE.id} />)
    // El item es <div class="entity-item active">
    const item = screen.getByText('Horno A').closest('.entity-item')
    expect(item?.className).toContain('active')
  })

  // ── Campo de búsqueda ─────────────────────────────────────────────────────

  it('llama onSearchChange al escribir en el campo de búsqueda', () => {
    const onSearchChange = vi.fn()
    render(<EntityList {...defaultProps} onSearchChange={onSearchChange} />)
    fireEvent.change(getSearchInput(), { target: { value: 'Horno' } })
    expect(onSearchChange).toHaveBeenCalledWith('Horno')
  })

  it('Escape en el campo de búsqueda limpia la búsqueda', () => {
    const onSearchChange = vi.fn()
    render(<EntityList {...defaultProps} search="Horno" onSearchChange={onSearchChange} />)
    fireEvent.keyDown(getSearchInput(), { key: 'Escape' })
    expect(onSearchChange).toHaveBeenCalledWith('')
  })

  it('el campo de búsqueda muestra el valor actual de search', () => {
    render(<EntityList {...defaultProps} search="Horno" />)
    expect(getSearchInput()).toHaveValue('Horno')
  })

  // ── Nueva entidad ─────────────────────────────────────────────────────────

  it('llama onNewEntity al hacer clic en "+ Nueva entidad"', () => {
    const onNewEntity = vi.fn()
    render(<EntityList {...defaultProps} onNewEntity={onNewEntity} />)
    fireEvent.click(screen.getByRole('button', { name: /nueva entidad/i }))
    expect(onNewEntity).toHaveBeenCalledTimes(1)
  })

  it('muestra contador de carga cuando loadCount está definido', () => {
    render(<EntityList {...defaultProps} loading loadCount={1200} />)
    expect(screen.getByText(/cargando… 1200/i)).toBeInTheDocument()
  })

})
