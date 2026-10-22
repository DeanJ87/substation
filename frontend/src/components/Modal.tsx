// A modal over the page (spec 012): the page stays behind it, Escape or the backdrop closes it, and the page doesn't
// scroll underneath while it's open. Tab stays inside it (a focus trap), and focus goes back to whatever opened it
// when it closes (007-DR-38).
import { useEffect, useRef, type ReactNode } from 'react'
import s from './Modal.module.css'

const FOCUSABLE =
  'a[href], button, input, select, textarea, summary, [tabindex]:not([tabindex="-1"]), [contenteditable="true"]'

function trap(e: KeyboardEvent, root: HTMLElement | null) {
  if (!root) return
  const all = Array.from(root.querySelectorAll<HTMLElement>(FOCUSABLE)).filter(
    (el) => !el.hasAttribute('disabled') && el.getClientRects().length > 0,
  )
  if (!all.length) {
    e.preventDefault()
    root.focus()
    return
  }
  const first = all[0]
  const last = all[all.length - 1]
  const at = document.activeElement
  if (e.shiftKey && (at === first || at === root || !root.contains(at))) {
    e.preventDefault()
    last.focus()
  } else if (!e.shiftKey && (at === last || !root.contains(at))) {
    e.preventDefault()
    first.focus()
  }
}

/** `size`: 'sm' a short dialog (a question, a small form: about 480 px, as tall as its content), 'md' a medium
 * form (about 760 px), 'lg' the full-size viewer (the default). */
export function Modal({
  label,
  onClose,
  children,
  size = 'lg',
}: {
  label: string
  onClose: () => void
  children: ReactNode
  size?: 'sm' | 'md' | 'lg'
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
      if (e.key === 'Tab') trap(e, panel.current)
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
      <div
        ref={panel}
        className={`${s.panel} ${s[size] ?? ''}`}
        role="dialog"
        aria-modal="true"
        aria-label={label}
        tabIndex={-1}
      >
        <button type="button" className={s.close} aria-label="Close" onClick={onClose}>
          ×
        </button>
        {children}
      </div>
    </div>
  )
}
