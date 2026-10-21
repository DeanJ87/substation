// A small "?" beside a heading or field: the explanation shows on hover, focus or click, instead of a paragraph
// sitting on the page. Escape, clicking elsewhere or clicking it again closes it.
import { useEffect, useId, useLayoutEffect, useRef, useState, type ReactNode } from 'react'
import s from './Help.module.css'

export function Help({ topic, children }: { topic: string; children: ReactNode }) {
  const [pinned, setPinned] = useState(false)
  const [hover, setHover] = useState(false)
  const id = useId()
  const box = useRef<HTMLSpanElement>(null)
  const tip = useRef<HTMLSpanElement>(null)
  const open = pinned || hover
  // keep the bubble on screen: it starts at the button and moves left as far as the right edge needs
  useLayoutEffect(() => {
    const el = tip.current
    if (!open || !el) return
    el.style.left = '0px'
    const r = el.getBoundingClientRect()
    const over = r.right - (document.documentElement.clientWidth - 16)
    if (over > 0) el.style.left = `${-Math.min(over, r.left - 16)}px`
  }, [open])
  useEffect(() => {
    if (!open) return
    const key = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        setPinned(false)
        setHover(false)
      }
    }
    const away = (e: PointerEvent) => {
      if (!box.current?.contains(e.target as Node)) {
        setPinned(false)
        setHover(false)
      }
    }
    document.addEventListener('keydown', key)
    document.addEventListener('pointerdown', away)
    return () => {
      document.removeEventListener('keydown', key)
      document.removeEventListener('pointerdown', away)
    }
  }, [open])
  return (
    <span
      ref={box}
      className={s.help}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
    >
      <button
        type="button"
        className={s.button}
        aria-label={`Help: ${topic}`}
        aria-expanded={open}
        aria-describedby={open ? id : undefined}
        onFocus={() => setHover(true)}
        onBlur={() => setHover(false)}
        onClick={() => setPinned((p) => !p)}
      >
        ?
      </button>
      {open && (
        <span ref={tip} id={id} role="tooltip" className={s.tip}>
          {children}
        </span>
      )}
    </span>
  )
}
