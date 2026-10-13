// One theme for the whole app: the header's N key and Settings → Appearance change the same value.
import { createContext, useContext, type ReactNode } from 'react'
import type { Theme } from './theme'
import { useTheme } from './useTheme'

const Ctx = createContext<{ theme: Theme; setTheme: (t: Theme) => void }>({
  theme: 'dark',
  setTheme: () => {},
})

export function ThemeProvider({ children }: { children: ReactNode }) {
  return <Ctx.Provider value={useTheme()}>{children}</Ctx.Provider>
}

export const useAppTheme = () => useContext(Ctx)
