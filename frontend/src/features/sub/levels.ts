// Display levels for the sub viewer (012-DR-08): a black point and a brightness applied to the preview on screen
// only. The preview is already stretched to 8 bits; this curve runs on those values, so nothing is sent to the
// server and no file or stored preview changes.
import { useCallback, useState } from 'react'

/** black: the 8-bit value drawn as black (negative lifts the shadows); bright: −100…+100, a midtone (gamma) shift. */
export type Levels = { black: number; bright: number }

export const NEUTRAL: Levels = { black: 0, bright: 0 }
export const BLACK_MIN = -64
export const BLACK_MAX = 128
export const BRIGHT_MIN = -100
export const BRIGHT_MAX = 100
/** How far [ and ] move the black point. */
export const BLACK_STEP = 2

const clamp = (x: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, x))

/** The gamma for a brightness: +50 → 0.5 (brighter midtones), −50 → 2 (darker), 0 → 1. */
export function gammaOf(bright: number): number {
  return 2 ** (-clamp(bright, BRIGHT_MIN, BRIGHT_MAX) / 50)
}

/** One 8-bit value through the curve: out = clamp((in − b) / (255 − b))^γ, on the 0–255 scale. */
export function levelOut(v: number, l: Levels): number {
  const b = clamp(l.black, BLACK_MIN, BLACK_MAX)
  const x = clamp((v - b) / (255 - b), 0, 1)
  return 255 * x ** gammaOf(l.bright)
}

export function isNeutral(l: Levels): boolean {
  return l.black === 0 && l.bright === 0
}

/** The curve as an SVG feComponentTransfer table: entry k is the output for the 8-bit input k, on 0–1. A table
 * of 256 values maps each 8-bit input exactly onto its entry, so the browser does the pixel work. */
export function tableValues(l: Levels): string {
  return Array.from({ length: 256 }, (_, k) => +(levelOut(k, l) / 255).toFixed(5)).join(' ')
}

export function signed(n: number): string {
  return n > 0 ? `+${n}` : n < 0 ? `−${-n}` : '0'
}

export function clampLevels(l: Levels): Levels {
  return {
    black: Math.round(clamp(l.black, BLACK_MIN, BLACK_MAX)),
    bright: Math.round(clamp(l.bright, BRIGHT_MIN, BRIGHT_MAX)),
  }
}

// remembered per browser, per dataset and filter; held in memory too, for browsers that refuse storage
const memory = new Map<string, Levels>()
const storageKey = (key: string) => `substation.sub-levels.${key}`

export function readLevels(key: string): Levels {
  const held = memory.get(key)
  if (held) return held
  try {
    const raw = window.localStorage.getItem(storageKey(key))
    if (raw) {
      const p = JSON.parse(raw) as Partial<Levels>
      if (typeof p.black === 'number' && typeof p.bright === 'number') return clampLevels(p as Levels)
    }
  } catch {
    // no storage: the default
  }
  return NEUTRAL
}

function writeLevels(key: string, l: Levels) {
  memory.set(key, l)
  try {
    if (isNeutral(l)) window.localStorage.removeItem(storageKey(key))
    else window.localStorage.setItem(storageKey(key), JSON.stringify(l))
  } catch {
    // no storage: kept for this page's life only
  }
}

/** Test hook: forget what's held in memory. */
export function forgetLevels() {
  memory.clear()
}

/** The levels for `key` (dataset and filter). While the key is unknown (the next sub loading) the last levels hold,
 * so stepping with J and K keeps them. */
export function useLevels(key: string | null): [Levels, (l: Levels) => void] {
  const [st, setSt] = useState<{ key: string | null; l: Levels }>(() => ({
    key,
    l: key ? readLevels(key) : NEUTRAL,
  }))
  let cur = st
  if (key && key !== st.key) {
    cur = { key, l: readLevels(key) }
    setSt(cur)
  }
  const set = useCallback(
    (l: Levels) => {
      const next = clampLevels(l)
      setSt((o) => {
        const k = key ?? o.key
        if (k) writeLevels(k, next)
        return { key: k, l: next }
      })
    },
    [key],
  )
  return [cur.l, set]
}
