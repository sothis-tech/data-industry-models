import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { ConfirmModal } from '../../components/ConfirmModal'

describe('ConfirmModal', () => {
  const defaultProps = {
    title: '¿Eliminar entidad?',
    message: 'Esta acción no se puede deshacer.',
    onConfirm: vi.fn(),
    onCancel: vi.fn(),
  }

  it('renders title', () => {
    render(<ConfirmModal {...defaultProps} />)
    expect(screen.getByText('¿Eliminar entidad?')).toBeInTheDocument()
  })

  it('renders message', () => {
    render(<ConfirmModal {...defaultProps} />)
    expect(screen.getByText('Esta acción no se puede deshacer.')).toBeInTheDocument()
  })

  it('renders cancel button', () => {
    render(<ConfirmModal {...defaultProps} />)
    expect(screen.getByRole('button', { name: 'Cancelar' })).toBeInTheDocument()
  })

  it('renders confirm button with default label', () => {
    render(<ConfirmModal {...defaultProps} />)
    expect(screen.getByRole('button', { name: 'Confirmar' })).toBeInTheDocument()
  })

  it('calls onConfirm when confirm button is clicked', () => {
    const onConfirm = vi.fn()
    render(<ConfirmModal {...defaultProps} onConfirm={onConfirm} />)
    fireEvent.click(screen.getByRole('button', { name: 'Confirmar' }))
    expect(onConfirm).toHaveBeenCalledTimes(1)
  })

  it('calls onCancel when cancel button is clicked', () => {
    const onCancel = vi.fn()
    render(<ConfirmModal {...defaultProps} onCancel={onCancel} />)
    fireEvent.click(screen.getByRole('button', { name: 'Cancelar' }))
    expect(onCancel).toHaveBeenCalledTimes(1)
  })

  it('shows custom confirmLabel when provided', () => {
    render(<ConfirmModal {...defaultProps} confirmLabel="Borrar" />)
    expect(screen.getByRole('button', { name: 'Borrar' })).toBeInTheDocument()
  })

  it('shows "Procesando…" text and disables button when loading is true', () => {
    render(<ConfirmModal {...defaultProps} loading={true} />)
    const processingBtn = screen.getByRole('button', { name: 'Procesando…' })
    expect(processingBtn).toBeDisabled()
  })

  it('accepts JSX as message', () => {
    render(
      <ConfirmModal
        {...defaultProps}
        message={<span data-testid="jsx-msg">Mensaje <strong>importante</strong></span>}
      />,
    )
    expect(screen.getByTestId('jsx-msg')).toBeInTheDocument()
    expect(screen.getByText('importante')).toBeInTheDocument()
  })

  it('applies danger class to confirm button when danger prop is true', () => {
    render(<ConfirmModal {...defaultProps} danger confirmLabel="Eliminar" />)
    const btn = screen.getByRole('button', { name: 'Eliminar' })
    expect(btn.className).toContain('danger')
  })

  it('calls onCancel when Escape key is pressed', () => {
    const onCancel = vi.fn()
    render(<ConfirmModal {...defaultProps} onCancel={onCancel} />)
    const overlay = document.querySelector('.modal-overlay')!
    fireEvent.keyDown(overlay, { key: 'Escape' })
    expect(onCancel).toHaveBeenCalledTimes(1)
  })
})
