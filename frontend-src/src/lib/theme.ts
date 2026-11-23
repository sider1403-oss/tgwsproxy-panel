import { useEffect, useState } from 'react'

export type Theme = 'dark' | 'light'
const KEY = 'tgws-theme'

export function currentTheme(): Theme {
  return document.documentElement.getAttribute('data-theme') === 'light' ? 'light' : 'dark'
}

export function applyTheme(theme: Theme) {
  document.documentElement.setAttribute('data-theme', theme)
  try {
    localStorage.setItem(KEY, theme)
  } catch {
    /* private mode */
  }
  const meta = document.querySelector('meta[name="theme-color"]')
  if (meta) meta.setAttribute('content', theme === 'light' ? '#f4f7fb' : '#070b12')
}

export function useTheme() {
  const [theme, setThemeState] = useState<Theme>(() => currentTheme())

  useEffect(() => {
    const observer = new MutationObserver(() => setThemeState(currentTheme()))
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] })
    return () => observer.disconnect()
  }, [])

  const setTheme = (next: Theme) => {
    applyTheme(next)
    setThemeState(next)
  }

  const toggle = () => setTheme(theme === 'light' ? 'dark' : 'light')

  return { theme, setTheme, toggle }
}
