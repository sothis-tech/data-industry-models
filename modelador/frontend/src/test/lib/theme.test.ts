import { beforeEach, describe, expect, it, vi } from 'vitest'
import {
  THEME_STORAGE_KEY,
  applyTheme,
  getStoredTheme,
  initTheme,
  readActiveTheme,
  setTheme,
  storeTheme,
  toggleTheme,
} from '../../lib/theme'

describe('theme', () => {
  beforeEach(() => {
    localStorage.clear()
    delete document.documentElement.dataset.theme
  })

  it('defaults to light when nothing is stored', () => {
    expect(getStoredTheme()).toBe('light')
  })

  it('reads and stores theme in localStorage', () => {
    storeTheme('light')
    expect(localStorage.getItem(THEME_STORAGE_KEY)).toBe('light')
    expect(getStoredTheme()).toBe('light')
  })

  it('applies theme to document root', () => {
    applyTheme('light')
    expect(document.documentElement.dataset.theme).toBe('light')
  })

  it('initTheme applies stored preference', () => {
    storeTheme('light')
    expect(initTheme()).toBe('light')
    expect(document.documentElement.dataset.theme).toBe('light')
  })

  it('setTheme persists and dispatches change event', () => {
    const handler = vi.fn()
    window.addEventListener('inn-theme-change', handler)

    setTheme('light')

    expect(getStoredTheme()).toBe('light')
    expect(readActiveTheme()).toBe('light')
    expect(handler).toHaveBeenCalledTimes(1)

    window.removeEventListener('inn-theme-change', handler)
  })

  it('toggleTheme switches between dark and light', () => {
    applyTheme('dark')
    expect(toggleTheme('dark')).toBe('light')
    expect(readActiveTheme()).toBe('light')
    expect(toggleTheme('light')).toBe('dark')
    expect(readActiveTheme()).toBe('dark')
  })
})
