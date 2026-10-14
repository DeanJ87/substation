// A modal over the page (spec 012): the page stays behind it, Escape or the backdrop closes it, and the page doesn't
// scroll underneath while it's open.
import { useEffect, useRef, type ReactNode } from 'react'
import s from './Modal.module.css'

export function Modal({
  label,
  onClose,
  children,
}: {
  label: string
  onClose: () => void
  children: ReactNode
}) {
  const panel = useRef<HTMLDivElement>(null)
  useEffect(() => {
    const before = document.activeElement as HTMLElement | null
    panel.current?.focus()
    const overflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    function key(e: KeyboardEvent) {
      // the 100% view inside listens first and stops the Escape that closes it
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', key)
    return () => {
      window.removeEventListener('keydown', key)
      document.body.style.overflow = overflow
      before?.focus?.()
    }
  }, [onClose])
  return (
    <div
      className={s.backdrop}
      role="presentation"
      onMouseDown={(e) => e.target === e.currentTarget && onClose()}
    >
      <div ref={panel} className={s.panel} role="dialog" aria-modal="true" aria-label={label} tabIndex={-1}>
        <button type="button" className={s.close} aria-label="Close" onClick={onClose}>
          ×
        </button>
        {children}
      </div>
    </div>
  )
}
