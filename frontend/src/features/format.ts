// Formatting in the voice guide's style: British dates, tabular figures, plain units.

export function integration(seconds: number): { h: number; m: number } {
  const total = Math.round(seconds / 60)
  return { h: Math.floor(total / 60), m: total % 60 }
}

export function integrationText(seconds: number): string {
  const { h, m } = integration(seconds)
  return h ? `${h}h ${String(m).padStart(2, '0')}m` : `${m}m`
}

export function nightText(isoDate: string | null | undefined): string {
  if (!isoDate) return 'no night'
  const d = new Date(`${isoDate}T12:00:00Z`)
  return d.toLocaleDateString('en-GB', { day: 'numeric', month: 'long', year: 'numeric', timeZone: 'UTC' })
}

export function timeText(iso: string | null | undefined): string {
  if (!iso) return '—'
  return new Date(iso).toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit', second: '2-digit' })
}

export function bytes(n: number | null | undefined): { value: string; unit: string } {
  if (n == null) return { value: '—', unit: '' }
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  let v = n
  let i = 0
  while (v >= 1000 && i < units.length - 1) {
    v /= 1000
    i++
  }
  return { value: v >= 100 ? v.toFixed(0) : v.toFixed(1), unit: units[i] }
}

export function temp(c: number | null | undefined): string {
  return c == null ? '—' : `${c.toFixed(1).replace('-', '−')} °C`
}

export function fileName(path: string): string {
  return path.split('/').pop() ?? path
}

/** "just now", "12 min ago", "3 h ago", "2 days ago" (007-DR-14 writing rules) */
export function agoText(iso: string | null | undefined, now: number = Date.now()): string {
  if (!iso) return '—'
  const s = Math.max(0, (now - new Date(iso).getTime()) / 1000)
  if (s < 60) return 'just now'
  if (s < 3600) return `${Math.round(s / 60)} min ago`
  if (s < 86400) return `${Math.round(s / 3600)} h ago`
  const d = Math.round(s / 86400)
  return `${d} day${d === 1 ? '' : 's'} ago`
}

/** A signed number with a real minus sign (U+2212) and en-GB grouping: "−20.0", "+1,234" (007-DR-14). */
export function signed(n: number | null | undefined, digits = 0, plus = false): string {
  if (n == null || Number.isNaN(n)) return '—'
  const s = Math.abs(n).toLocaleString('en-GB', {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  })
  return n < 0 ? `−${s}` : plus && n > 0 ? `+${s}` : s
}

/** "3 Oct 2026" (short) for tables; nightText gives "3 October 2026" for headings. */
export function shortDateText(iso: string | null | undefined): string {
  if (!iso) return '—'
  return new Date(`${iso.slice(0, 10)}T12:00:00Z`).toLocaleDateString('en-GB', {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
    timeZone: 'UTC',
  })
}

/** "45 s", "12 min", "1 h 05 min", "2 days 3 h": durations as people say them. */
export function durationText(seconds: number | null | undefined): string {
  if (seconds == null) return '—'
  const s = Math.round(seconds)
  if (s < 60) return `${s} s`
  if (s < 3600) return `${Math.round(s / 60)} min`
  if (s < 86400)
    return `${Math.floor(s / 3600)} h ${String(Math.round((s % 3600) / 60)).padStart(2, '0')} min`
  return `${Math.floor(s / 86400)} day${s < 172800 ? '' : 's'} ${Math.round((s % 86400) / 3600)} h`
}

/** "Oct 2025" or "Oct 2025 to Jan 2026": the months a collection or project spans. */
export function monthSpan(a: string | null | undefined, b: string | null | undefined): string {
  const f = (d: string) =>
    new Date(`${d}T12:00:00Z`).toLocaleDateString('en-GB', { month: 'short', year: 'numeric' })
  if (!a || !b) return ''
  return f(a) === f(b) ? f(a) : `${f(a)} to ${f(b)}`
}
