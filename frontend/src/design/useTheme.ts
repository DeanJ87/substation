import { useCallback, useEffect, useRef, useState } from 'react'
import { useHotkeys } from 'react-hotkeys-hook'
import { api } from '../api/client'
import { applyTheme, readTheme, toggleNight, type Theme } from './theme'

/** The theme: applied from this browser's copy before the first paint (index.html), then from the user's saved
 * choice once signed in, and saved back whenever it changes, so it follows the user (007-DR-06). */
export function useTheme() {
  const [theme, setThemeState] = useState<Theme>(readTheme)
  const previous = useRef<Theme>(theme === 'night' ? 'dark' : theme)
  const loaded = useRef(false)
  const touched = useRef(false) // changed here before the saved choice arrived: that change wins

  useEffect(() => applyTheme(theme), [theme])

  useEffect(() => {
    let live = true
    void api.GET('/users/me/preferences').then(({ data }) => {
      if (!live) return
      if (data?.theme && !touched.current) setThemeState(data.theme as Theme)
      loaded.current = true
    })
    return () => {
      live = false
    }
  }, [])

  const first = useRef(true)
  useEffect(() => {
    if (first.current) {
      first.current = false
      return
    }
    touched.current = true
    void api.PUT('/users/me/preferences', { body: { theme } })
  }, [theme])

  const setTheme = useCallback((t: Theme) => {
    if (t !== 'night') previous.current = t
    setThemeState(t)
  }, [])

  useHotkeys('n', () => setThemeState((t) => toggleNight(t, previous.current)), { preventDefault: true })

  return { theme, setTheme }
}
