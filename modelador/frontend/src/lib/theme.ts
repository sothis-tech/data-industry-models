export type Theme = 'dark' | 'light'

export const DEFAULT_THEME: Theme = 'light'
export const THEME_STORAGE_KEY = 'inn-modelador-theme'
export const THEME_CHANGE_EVENT = 'inn-theme-change'

export function getStoredTheme(): Theme {
  try {
    const stored = localStorage.getItem(THEME_STORAGE_KEY)
    if (stored === 'light' || stored === 'dark') return stored
  } catch {
    /* localStorage no disponible */
  }
  return DEFAULT_THEME
}

export function applyTheme(theme: Theme): void {
  document.documentElement.dataset.theme = theme
}

export function storeTheme(theme: Theme): void {
  try {
    localStorage.setItem(THEME_STORAGE_KEY, theme)
  } catch {
    /* localStorage no disponible */
  }
}

export function initTheme(): Theme {
  const theme = getStoredTheme()
  applyTheme(theme)
  return theme
}

export function setTheme(theme: Theme): void {
  applyTheme(theme)
  storeTheme(theme)
  window.dispatchEvent(new Event(THEME_CHANGE_EVENT))
}

export function toggleTheme(current: Theme): Theme {
  const next = current === 'dark' ? 'light' : 'dark'
  setTheme(next)
  return next
}

export function readActiveTheme(): Theme {
  const fromDom = document.documentElement.dataset.theme
  if (fromDom === 'light' || fromDom === 'dark') return fromDom
  return getStoredTheme()
}
