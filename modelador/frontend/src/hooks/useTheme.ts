import { useCallback, useSyncExternalStore } from 'react'
import { readActiveTheme, setTheme, toggleTheme, THEME_CHANGE_EVENT, DEFAULT_THEME, type Theme } from '../lib/theme'

function subscribe(onStoreChange: () => void) {
  window.addEventListener(THEME_CHANGE_EVENT, onStoreChange)
  return () => window.removeEventListener(THEME_CHANGE_EVENT, onStoreChange)
}

export function useTheme() {
  const theme = useSyncExternalStore(subscribe, readActiveTheme, () => DEFAULT_THEME)

  const apply = useCallback((next: Theme) => {
    setTheme(next)
  }, [])

  const toggle = useCallback(() => {
    toggleTheme(readActiveTheme())
  }, [])

  return { theme, setTheme: apply, toggleTheme: toggle }
}
