import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it } from 'vitest'
import { ThemeToggle } from '../../components/ThemeToggle'
import { applyTheme } from '../../lib/theme'

describe('ThemeToggle', () => {
  beforeEach(() => {
    localStorage.clear()
    applyTheme('light')
  })

  it('shows moon icon and label for switching to dark theme', () => {
    render(<ThemeToggle />)
    expect(screen.getByRole('button', { name: 'Cambiar a tema oscuro' })).toBeInTheDocument()
    expect(screen.getByText('Tema oscuro')).toBeInTheDocument()
  })

  it('toggles to dark theme on click', () => {
    render(<ThemeToggle />)
    fireEvent.click(screen.getByRole('button', { name: 'Cambiar a tema oscuro' }))
    expect(document.documentElement.dataset.theme).toBe('dark')
    expect(screen.getByRole('button', { name: 'Cambiar a tema claro' })).toBeInTheDocument()
  })
})
