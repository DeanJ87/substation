// What the map's address can say (spec 015 FR-001, FR-002): where to look, and which nights to show.
export type MapSearch = {
  lat?: number
  lon?: number
  zoom?: number
  date?: string // one night (YYYY-MM-DD)
  from?: string // or a range of nights, either end open
  to?: string
}

const DAY = /^\d{4}-\d{2}-\d{2}$/

function num(v: unknown, lo: number, hi: number): number | undefined {
  const n = typeof v === 'number' ? v : typeof v === 'string' && v.trim() !== '' ? Number(v) : NaN
  return Number.isFinite(n) && n >= lo && n <= hi ? n : undefined
}

const day = (v: unknown) => (typeof v === 'string' && DAY.test(v) ? v : undefined)

export function mapSearch(q: Record<string, unknown>): MapSearch {
  const lat = num(q.lat, -90, 90)
  const lon = num(q.lon, -180, 180)
  const both = lat !== undefined && lon !== undefined
  const date = day(q.date)
  return {
    lat: both ? lat : undefined,
    lon: both ? lon : undefined,
    zoom: num(q.zoom, 1, 18),
    date,
    from: date ? undefined : day(q.from),
    to: date ? undefined : day(q.to),
  }
}

/** The nights to ask the map API for: one date, or a range. */
export function period(s: MapSearch): { since?: string; until?: string } {
  if (s.date) return { since: s.date, until: s.date }
  return { since: s.from, until: s.to }
}

const pad = (n: number) => String(n).padStart(2, '0')
export const isoDay = (d: Date) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`

/** Quick choices for the date control, relative to `today`. */
export function presets(today: Date): { label: string; search: MapSearch }[] {
  const back = (days: number) =>
    isoDay(new Date(today.getFullYear(), today.getMonth(), today.getDate() - days))
  const monthStart = isoDay(new Date(today.getFullYear(), today.getMonth(), 1))
  return [
    { label: 'Last 30 days', search: { from: back(30), to: isoDay(today) } },
    { label: 'This month', search: { from: monthStart, to: isoDay(today) } },
    { label: 'This year', search: { from: `${today.getFullYear()}-01-01`, to: isoDay(today) } },
  ]
}

const longDay = (d: string) =>
  new Date(`${d}T12:00:00`).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' })

/** "11 Oct 2026", "1 Oct 2026 to 15 Oct 2026", "from 1 Oct 2026", or null for every night. */
export function periodText(s: MapSearch): string | null {
  if (s.date) return longDay(s.date)
  if (s.from && s.to) return s.from === s.to ? longDay(s.from) : `${longDay(s.from)} to ${longDay(s.to)}`
  if (s.from) return `from ${longDay(s.from)}`
  if (s.to) return `up to ${longDay(s.to)}`
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
