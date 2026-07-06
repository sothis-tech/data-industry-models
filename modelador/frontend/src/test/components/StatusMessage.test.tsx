import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { StatusMessage } from '../../components/StatusMessage'

// La prop de variante se llama `variant` (no `type`).
// El componente siempre renderiza un <p>, incluso con mensaje vacío.

describe('StatusMessage', () => {
  it('renders the message text', () => {
    render(<StatusMessage message="Operación completada" />)
    expect(screen.getByText('Operación completada')).toBeInTheDocument()
  })

  it('renders a paragraph element', () => {
    const { container } = render(<StatusMessage message="test" />)
    expect(container.querySelector('p')).toBeInTheDocument()
  })

  it('applies error variant class', () => {
    render(<StatusMessage message="Error crítico" variant="error" />)
    const el = screen.getByText('Error crítico')
    expect(el.className).toContain('error')
  })

  it('applies success variant class', () => {
    render(<StatusMessage message="Guardado correctamente" variant="success" />)
    const el = screen.getByText('Guardado correctamente')
    expect(el.className).toContain('success')
  })

  it('applies info class by default', () => {
    render(<StatusMessage message="Información" />)
    const el = screen.getByText('Información')
    expect(el.className).toContain('info')
  })
})
