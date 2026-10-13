// Theme switch: dark (default), light and night vision (red on black). N toggles night vision anywhere.
// The choice is a per-viewer convenience kept in localStorage; storage can be unavailable, so every
// access is guarded and the default still renders.
export type Theme = 'dark' | 'light' | 'night'

const KEY = 'sst-theme'
const THEMES: Theme[] = ['dark', 'light', 'night']

export function readTheme(): Theme {
  try {
    const v = localStorage.getItem(KEY)
    return THEMES.includes(v as Theme) ? (v as Theme) : 'dark'
  } catch {
    return 'dark'
  }
}

export function applyTheme(theme: Theme): void {
  const root = document.documentElement
  if (theme === 'dark') root.removeAttribute('data-theme')
  else root.setAttribute('data-theme', theme)
  try {
    localStorage.setItem(KEY, theme)
  } catch {
    /* storage unavailable: the theme still applies for this visit */
  }
}

export function toggleNight(current: Theme, previous: Theme): Theme {
  return current === 'night' ? (previous === 'night' ? 'dark' : previous) : 'night'
}
