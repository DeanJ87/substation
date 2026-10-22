// Formatting, one module (007-DR-39). Every screen writes dates, times, durations and numbers through these, so
// the same thing always reads the same way:
//   dates      "18 Sep 2026" · with a time "18 Sep 2026, 21:12" · a night in a list "18 Sep" · a month "Sep 2026"
//   times      "21:12" (24 h, the browser's local time; never seconds)
//   durations  "45s", "12m", "4h 30m", "5h", "2d 3h": compact, minutes zero-padded after hours, no "00m"
//   exposures  "300 s", "2.5 s", "1 ms": a sub's shutter time, with a space
//   numbers    en-GB grouping "1,390", a real minus sign "−9", "—" when there's no value
//   binning    "1×1"
// Months are spelt out by hand: en-GB's Intl writes September as "Sept".

import { filterName } from '../components/filters'

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
const DASH = '—'

/** A calendar day ("2026-09-18", or the date part of an ISO time) as a UTC date. */
function day(iso: string): Date {
  return new Date(`${iso.slice(0, 10)}T12:00:00Z`)
}

const pad = (n: number) => String(n).padStart(2, '0')

/** "18 Sep 2026": a night or a day, in headings and tables alike. */
export function dateText(iso: string | null | undefined): string {
  if (!iso) return DASH
  const d = day(iso)
  if (Number.isNaN(d.getTime())) return DASH
  return `${d.getUTCDate()} ${MONTHS[d.getUTCMonth()]} ${d.getUTCFullYear()}`
}

/** A night's date. Same as dateText, with "no night" for a sub that has none. */
export function nightText(isoDate: string | null | undefined): string {
  return isoDate ? dateText(isoDate) : 'no night'
}

/** "3 Oct 2026" (kept for older callers; the same as dateText). */
export const shortDateText = dateText

/** "18 Sep": a night in a list where the year is obvious. */
export function nightShort(isoDate: string | null | undefined): string {
  if (!isoDate) return DASH
  const d = day(isoDate)
  return `${d.getUTCDate()} ${MONTHS[d.getUTCMonth()]}`
}

/** "Sep 2026" */
export function monthText(iso: string | null | undefined): string {
  if (!iso) return DASH
  const d = day(iso)
  return `${MONTHS[d.getUTCMonth()]} ${d.getUTCFullYear()}`
}

/** "Oct 2025" or "Oct 2025 to Jan 2026": the months a collection or project spans. */
export function monthSpan(a: string | null | undefined, b: string | null | undefined): string {
  if (!a || !b) return ''
  const x = monthText(a)
  const y = monthText(b)
  return x === y ? x : `${x} to ${y}`
}

/** "18 Sep 2026 to 2 Oct 2026", or one date when they're the same night. */
export function dateSpan(a: string | null | undefined, b: string | null | undefined): string {
  if (!a) return dateText(b)
  if (!b || a.slice(0, 10) === b.slice(0, 10)) return dateText(a)
  return `${dateText(a)} to ${dateText(b)}`
}

/** "21:12": a moment, in local time, to the minute. */
export function clockText(iso: string | number | Date | null | undefined): string {
  if (iso == null || iso === '') return DASH
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return DASH
  return `${pad(d.getHours())}:${pad(d.getMinutes())}`
}

/** Kept for older callers: now the same as clockText (no seconds). */
export const timeText = clockText

/** "18 Sep 2026, 21:12": a moment with its day, local time. */
export function dateTimeText(iso: string | number | Date | null | undefined): string {
  if (iso == null || iso === '') return DASH
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return DASH
  return `${d.getDate()} ${MONTHS[d.getMonth()]} ${d.getFullYear()}, ${clockText(d)}`
}

/** "21:12 to 21:48" */
export function clockSpan(
  a: string | number | null | undefined,
  b: string | number | null | undefined,
): string {
  return `${clockText(a)} to ${clockText(b)}`
}

export function integration(seconds: number): { h: number; m: number } {
  const total = Math.round(seconds / 60)
  return { h: Math.floor(total / 60), m: total % 60 }
}

/** Integration time: "5h", "4h 30m", "40m", "0m". */
export function integrationText(seconds: number | null | undefined): string {
  if (seconds == null || Number.isNaN(seconds)) return DASH
  const { h, m } = integration(seconds)
  if (!h) return `${m}m`
  return m ? `${h}h ${pad(m)}m` : `${h}h`
}

/** Any duration: "45s", "12m", "1h 05m", "5h", "1d 1h". Seconds only under a minute. */
export function durationText(seconds: number | null | undefined): string {
  if (seconds == null || Number.isNaN(seconds)) return DASH
  const s = Math.max(0, Math.round(seconds))
  if (s < 60) return `${s}s`
  if (s < 86400) return integrationText(s)
  const d = Math.floor(s / 86400)
  const h = Math.round((s % 86400) / 3600)
  return h ? `${d}d ${h}h` : `${d}d`
}

/** A sub's exposure: "300 s", "2.5 s", "1 ms". */
export function exposureText(seconds: number | null | undefined): string {
  if (seconds == null || Number.isNaN(seconds)) return DASH
  const short = (n: number) => n.toLocaleString('en-GB', { maximumFractionDigits: 2 })
  if (seconds > 0 && seconds < 1) return `${short(seconds * 1000)} ms`
  return `${short(seconds)} s`
}

/** "just now", "12m ago", "3h ago", "2 days ago" */
export function agoText(iso: string | null | undefined, now: number = Date.now()): string {
  if (!iso) return DASH
  const s = Math.max(0, (now - new Date(iso).getTime()) / 1000)
  if (s < 60) return 'just now'
  if (s < 3600) return `${Math.round(s / 60)}m ago`
  if (s < 86400) return `${Math.round(s / 3600)}h ago`
  const d = Math.round(s / 86400)
  return `${d} day${d === 1 ? '' : 's'} ago`
}

/** A number with en-GB grouping and a real minus sign: "1,390", "−83", "3.68". */
export function numText(n: number | null | undefined, digits = 0): string {
  if (n == null || Number.isNaN(n)) return DASH
  const s = Math.abs(n).toLocaleString('en-GB', {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  })
  return n < 0 && s.replace(/[0.,]/g, '') !== '' ? `−${s}` : s
}

/** A count: "1,390". */
export const countText = (n: number | null | undefined) => numText(n, 0)

/** A signed number with a real minus sign (U+2212) and en-GB grouping: "−20.0", "+1,234" (007-DR-14). */
export function signed(n: number | null | undefined, digits = 0, plus = false): string {
  if (n == null || Number.isNaN(n)) return DASH
  const s = numText(n, digits)
  return plus && n > 0 ? `+${s}` : s
}

/** "50%" from a fraction 0..1. */
export function pctText(fraction: number | null | undefined, digits = 0): string {
  if (fraction == null || Number.isNaN(fraction)) return DASH
  return `${numText(fraction * 100, digits)}%`
}

/** "12°", "−9°", "2.5°" */
export function angleText(deg: number | null | undefined, digits = 0): string {
  if (deg == null || Number.isNaN(deg)) return DASH
  return `${numText(deg, digits)}°`
}

/** "1×1" from 1, "1x1", [1, 1] or (1, 2). */
export function binText(x: number | string | null | undefined, y?: number | null): string {
  if (x == null || x === '') return DASH
  if (typeof x === 'string') return x.replace(/\s*[x×]\s*/i, '×')
  return `${x}×${y ?? x}`
}

/** "3.68″" for an FWHM in arcseconds. */
export function arcsecText(v: number | null | undefined, digits = 2): string {
  return v == null || Number.isNaN(v) ? DASH : `${numText(v, digits)}″`
}

export function bytes(n: number | null | undefined): { value: string; unit: string } {
  if (n == null) return { value: DASH, unit: '' }
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  let v = n
  let i = 0
  while (v >= 1000 && i < units.length - 1) {
    v /= 1000
    i++
  }
  return { value: i === 0 || v >= 100 ? v.toFixed(0) : v.toFixed(1), unit: units[i] }
}

/** "20.8 GB" */
export function bytesText(n: number | null | undefined): string {
  const b = bytes(n)
  return b.unit ? `${b.value} ${b.unit}` : b.value
}

/** "−19.9 °C" */
export function temp(c: number | null | undefined): string {
  return c == null ? DASH : `${numText(c, 1)} °C`
}

/** "1 sub", "24 subs", "1,390 subs" */
export function plural(n: number, word: string, many = `${word}s`): string {
  return `${countText(n)} ${n === 1 ? word : many}`
}

export function fileName(path: string): string {
  return path.split('/').pop() ?? path
}

/** A dataset's name, always in one order: target, panel, filter ("NGC 7000 · Panel 1 · Hα"). The rig is
 * secondary text beside it, never part of the name (007-DR-39). */
export function datasetLabel(d: {
  target?: string | null
  panel?: number | null
  filter?: string | null
}): string {
  return [d.target, d.panel ? `Panel ${d.panel}` : '', filterName(d.filter)].filter(Boolean).join(' · ')
}

/** When a block of subs was shot, shutter open to shutter close, as [start, end] in ms (B17). `mid` says each sub's
 * time is the middle of its exposure (the sky's placed subs) rather than its start (DATE-OBS). */
export function shutterSpan(
  subs: { time?: string | null; exptime_s?: number | null }[],
  mid = false,
): [number, number] | null {
  let a = Infinity
  let b = -Infinity
  for (const x of subs) {
    if (!x.time) continue
    const t = Date.parse(x.time)
    const e = (x.exptime_s ?? 0) * 1000
    const start = mid ? t - e / 2 : t
    a = Math.min(a, start)
    b = Math.max(b, start + e)
  }
  return a <= b ? [a, b] : null
}
