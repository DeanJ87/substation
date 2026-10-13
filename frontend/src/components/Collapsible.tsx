// A section that folds away (owner 2026-10-11). Remembered
// per browser, so a section you closed stays closed.
import { useState, type ReactNode } from 'react'
import s from './Collapsible.module.css'

const read = (id: string, fallback: boolean) => {
  try {
    const v = localStorage.getItem(`sst.open.${id}`)
    return v == null ? fallback : v === '1'
  } catch {
    return fallback
  }
}

export function Collapsible({
  id,
  title,
  meta,
  children,
  defaultOpen = true,
  className,
}: {
  id: string
  title: ReactNode
  meta?: ReactNode
  children: ReactNode
  defaultOpen?: boolean
  className?: string
}) {
  const [open, setOpen] = useState(() => read(id, defaultOpen))
  const toggle = () => {
    setOpen(!open)
    try {
      localStorage.setItem(`sst.open.${id}`, open ? '0' : '1')
    } catch {
      // private window: just don't remember
    }
  }
  return (
    <section className={`${s.section} ${className ?? ''}`} aria-labelledby={`${id}-h`}>
      <div className={s.head}>
        <button type="button" id={`${id}-h`} className={s.toggle} aria-expanded={open} onClick={toggle}>
          <svg className={s.chev} viewBox="0 0 12 12" aria-hidden="true">
            <path d="M4 2.5 7.5 6 4 9.5" fill="none" stroke="currentColor" strokeWidth="1.5" />
          </svg>
          <span>{title}</span>
        </button>
        {meta != null && <div className={s.meta}>{meta}</div>}
      </div>
      {open && <div className={s.body}>{children}</div>}
    </section>
  )
}
