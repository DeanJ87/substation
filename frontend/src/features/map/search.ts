// What the map's address can say (spec 015 FR-001, FR-002): where to look, and which nights to show; the nights
// and everything else the map is narrowed to are the shared scope (spec 018).
import { omit, readScope, scopeQuery, type Scope } from '../scope/scope'

export type MapSearch = Scope & {
  lat?: number // where to look: the view, not a filter
  lon?: number
  zoom?: number
}

function num(v: unknown, lo: number, hi: number): number | undefined {
  const n = typeof v === 'number' ? v : typeof v === 'string' && v.trim() !== '' ? Number(v) : NaN
  return Number.isFinite(n) && n >= lo && n <= hi ? n : undefined
}

export function mapSearch(q: Record<string, unknown>): MapSearch {
  const lat = num(q.lat, -90, 90)
  const lon = num(q.lon, -180, 180)
  const both = lat !== undefined && lon !== undefined
  // `from` and `to` are the older names for the range (spec 015)
  const scope = readScope({ ...q, date_from: q.date_from ?? q.from, date_to: q.date_to ?? q.to })
  return {
    ...(scope.date ? omit(scope, 'date_from', 'date_to') : scope), // one night wins over a range
    lat: both ? lat : undefined,
    lon: both ? lon : undefined,
    zoom: num(q.zoom, 1, 18),
  }
}

/** What to ask the map API for: the scope, without the view. */
export function mapQuery(s: MapSearch): Record<string, string | number> {
  return scopeQuery(readScope(s))
}

/** The scope besides its nights: what else the map is narrowed to (a rig, a collection…). */
export function besidesNights(s: MapSearch): Scope {
  return omit(readScope(s), 'date', 'date_from', 'date_to')
}

const pad = (n: number) => String(n).padStart(2, '0')
export const isoDay = (d: Date) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`

/** Quick choices for the date control, relative to `today`. */
export function presets(today: Date): { label: string; search: MapSearch }[] {
  const back = (days: number) =>
    isoDay(new Date(today.getFullYear(), today.getMonth(), today.getDate() - days))
  const monthStart = isoDay(new Date(today.getFullYear(), today.getMonth(), 1))
  return [
    { label: 'Last 30 days', search: { date_from: back(30), date_to: isoDay(today) } },
    { label: 'This month', search: { date_from: monthStart, date_to: isoDay(today) } },
    { label: 'This year', search: { date_from: `${today.getFullYear()}-01-01`, date_to: isoDay(today) } },
  ]
}

const longDay = (d: string) =>
  new Date(`${d}T12:00:00`).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' })

/** "11 Oct 2026", "1 Oct 2026 to 15 Oct 2026", "from 1 Oct 2026", or null for every night. */
export function periodText(s: MapSearch): string | null {
  if (s.date) return longDay(s.date)
  const { date_from: from, date_to: to } = s
  if (from && to) return from === to ? longDay(from) : `${longDay(from)} to ${longDay(to)}`
  if (from) return `from ${longDay(from)}`
  if (to) return `up to ${longDay(to)}`
  return null
}

/** The place nearest a point, if one is within about 5 km. */
export function nearest<T extends { lat: number; lon: number }>(
  list: T[],
  lat: number,
  lon: number,
): T | null {
  let best: T | null = null
  let bestD = 0.05
  for (const p of list) {
    const d = Math.hypot(p.lat - lat, (p.lon - lon) * Math.cos((lat * Math.PI) / 180))
    if (d < bestD) {
      best = p
      bestD = d
    }
  }
  return best
}
