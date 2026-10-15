// A mono picture shown in its filter's colour (2026-10-16): the grey image multiplied by the filter's tint, so stars
// and nebulosity take the colour and the black sky stays black. Pictures already in colour are left alone.
import type { ReactNode } from 'react'
import { filterTint } from './filterTint'
import s from './Tinted.module.css'

export function Tinted({ filter, children }: { filter: string | null | undefined; children: ReactNode }) {
  const tint = filterTint(filter)
  if (!tint) return <>{children}</>
  return (
    <span className={s.tinted} style={{ '--tint': tint } as React.CSSProperties} title={`${filter} filter`}>
      {children}
    </span>
  )
}
