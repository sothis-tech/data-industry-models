import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { SelectTypeModal } from '../../pages/entities/SelectTypeModal'

const TYPES = ['ManufacturingMachine', 'Area', 'Device']

describe('SelectTypeModal', () => {

  // ── Render ──────────────────────────────────────────────────────────────────

  it('renderiza el título', () => {
    render(<SelectTypeModal types={TYPES} onConfirm={vi.fn()} onClose={vi.fn()} />)
    expect(screen.getByText(/selecciona un tipo/i)).toBeInTheDocument()
  })

  it('renderiza el texto explicativo', () => {
    render(<SelectTypeModal types={TYPES} onConfirm={vi.fn()} onClose={vi.fn()} />)
    expect(screen.getByText(/para crear una entidad nueva/i)).toBeInTheDocument()
  })

  it('muestra todos los tipos como opciones del select', () => {
    render(<SelectTypeModal types={TYPES} onConfirm={vi.fn()} onClose={vi.fn()} />)
    expect(screen.getByRole('option', { name: 'ManufacturingMachine' })).toBeInTheDocument()
    expect(screen.getByRole('option', { name: 'Area' })).toBeInTheDocument()
    expect(screen.getByRole('option', { name: 'Device' })).toBeInTheDocument()
  })

  it('el primer tipo está seleccionado por defecto', () => {
    render(<SelectTypeModal types={TYPES} onConfirm={vi.fn()} onClose={vi.fn()} />)
    expect(screen.getByRole('combobox')).toHaveValue('ManufacturingMachine')
  })

  it('renderiza el botón Cancelar', () => {
    render(<SelectTypeModal types={TYPES} onConfirm={vi.fn()} onClose={vi.fn()} />)
    expect(screen.getByRole('button', { name: /cancelar/i })).toBeInTheDocument()
  })

  it('renderiza el botón Continuar', () => {
    render(<SelectTypeModal types={TYPES} onConfirm={vi.fn()} onClose={vi.fn()} />)
    expect(screen.getByRole('button', { name: /continuar/i })).toBeInTheDocument()
  })

  // ── Interacciones ───────────────────────────────────────────────────────────

  it('Cancelar llama onClose', () => {
    const onClose = vi.fn()
    render(<SelectTypeModal types={TYPES} onConfirm={vi.fn()} onClose={onClose} />)
    fireEvent.click(screen.getByRole('button', { name: /cancelar/i }))
    expect(onClose).toHaveBeenCalledTimes(1)
  })

  it('Continuar llama onConfirm con el tipo seleccionado por defecto', () => {
    const onConfirm = vi.fn()
    render(<SelectTypeModal types={TYPES} onConfirm={onConfirm} onClose={vi.fn()} />)
    fireEvent.click(screen.getByRole('button', { name: /continuar/i }))
    expect(onConfirm).toHaveBeenCalledWith('ManufacturingMachine')
  })

  it('cambiar la selección y confirmar envía el tipo correcto', () => {
    const onConfirm = vi.fn()
    render(<SelectTypeModal types={TYPES} onConfirm={onConfirm} onClose={vi.fn()} />)
    fireEvent.change(screen.getByRole('combobox'), { target: { value: 'Area' } })
    fireEvent.click(screen.getByRole('button', { name: /continuar/i }))
    expect(onConfirm).toHaveBeenCalledWith('Area')
  })

  it('Escape llama onClose', () => {
    const onClose = vi.fn()
    render(<SelectTypeModal types={TYPES} onConfirm={vi.fn()} onClose={onClose} />)
    const overlay = document.querySelector('.modal-overlay')!
    fireEvent.keyDown(overlay, { key: 'Escape' })
    expect(onClose).toHaveBeenCalledTimes(1)
  })

  it('clic en el overlay llama onClose', () => {
    const onClose = vi.fn()
    render(<SelectTypeModal types={TYPES} onConfirm={vi.fn()} onClose={onClose} />)
    const overlay = document.querySelector('.modal-overlay')!
    fireEvent.click(overlay)
    expect(onClose).toHaveBeenCalledTimes(1)
  })

  it('clic dentro del modal-box NO llama onClose', () => {
    const onClose = vi.fn()
    render(<SelectTypeModal types={TYPES} onConfirm={vi.fn()} onClose={onClose} />)
    const box = document.querySelector('.modal-box')!
    fireEvent.click(box)
    expect(onClose).not.toHaveBeenCalled()
  })

  // ── Casos borde ──────────────────────────────────────────────────────────────

  it('Continuar está deshabilitado cuando types está vacío', () => {
    render(<SelectTypeModal types={[]} onConfirm={vi.fn()} onClose={vi.fn()} />)
    expect(screen.getByRole('button', { name: /continuar/i })).toBeDisabled()
  })

  it('no llama onConfirm si Continuar está deshabilitado', () => {
    const onConfirm = vi.fn()
    render(<SelectTypeModal types={[]} onConfirm={onConfirm} onClose={vi.fn()} />)
    fireEvent.click(screen.getByRole('button', { name: /continuar/i }))
    expect(onConfirm).not.toHaveBeenCalled()
  })

  it('con un único tipo solo hay una opción', () => {
    render(<SelectTypeModal types={['Area']} onConfirm={vi.fn()} onClose={vi.fn()} />)
    const options = screen.getAllByRole('option')
    expect(options).toHaveLength(1)
    expect(options[0]).toHaveValue('Area')
  })

})
