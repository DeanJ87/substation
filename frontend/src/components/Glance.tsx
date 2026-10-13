// Hover a file name (or anything naming a frame) to see the frame (owner 2026-10-11). Shows after a short pause so passing over a list doesn't
// flash; follows the pointer and keeps on screen; keyboard focus shows it too.
import { useEffect, useRef, useState, type ReactNode } from 'react'
import { createPortal } from 'react-dom'
import { Spinner } from './ui'
import s from './Glance.module.css'

export const glanceUrl = (sha: string) => `/api/v1/frames/${sha}/glance`

const W = 320

export function Glance({ sha, label, children }: { sha: string; label?: string; children: ReactNode }) {
  const [at, setAt] = useState<{ x: number; y: number } | null>(null)
  const [loaded, setLoaded] = useState(false)
  const [failed, setFailed] = useState(false)
  const timer = useRef<number | null>(null)
  const pos = useRef({ x: 0, y: 0 })
  const stop = () => {
    if (timer.current) window.clearTimeout(timer.current)
    timer.current = null
    setAt(null)
  }
  // no timer left running after the row goes away
  useEffect(
    () => () => {
      if (timer.current) window.clearTimeout(timer.current)
    },
    [],
  )
  const show = (x: number, y: number) => {
    pos.current = { x, y }
    if (timer.current || at) return
    timer.current = window.setTimeout(() => setAt({ ...pos.current }), 250)
  }
  // keep the card inside the window: to the right of the pointer, or the left near the edge
  const left = at ? (at.x + 16 + W > window.innerWidth ? at.x - 16 - W : at.x + 16) : 0
  const top = at ? Math.min(at.y + 16, window.innerHeight - W * 0.75 - 40) : 0
  return (
    <span
      className={s.target}
      onPointerEnter={(e) => e.pointerType === 'mouse' && show(e.clientX, e.clientY)}
      onPointerMove={(e) => {
        pos.current = { x: e.clientX, y: e.clientY }
        if (at) setAt({ x: e.clientX, y: e.clientY })
      }}
      onPointerLeave={stop}
      onFocus={(e) => {
        const r = e.currentTarget.getBoundingClientRect()
        show(r.right, r.top)
      }}
      onBlur={stop}
    >
      {children}
      {at &&
        createPortal(
          <div className={s.card} style={{ left, top, width: W }} aria-hidden="true">
            {!loaded && (
              <div className={s.wait}>
                <Spinner label="Loading preview" />
              </div>
            )}
            {failed ? (
              <div className={s.wait}>No preview: this frame couldn't be drawn.</div>
            ) : (
              <img
                src={glanceUrl(sha)}
                alt=""
                onLoad={() => setLoaded(true)}
                onError={() => {
                  setLoaded(true)
                  setFailed(true)
                }}
                style={loaded ? undefined : { position: 'absolute', opacity: 0 }}
              />
            )}
            {label && <div className={s.label}>{label}</div>}
          </div>,
          document.body,
        )}
    </span>
  )
}
