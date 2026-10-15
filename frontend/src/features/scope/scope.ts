// One scope for every list (spec 018): the same filters, by the same names, in every page's address and every
// list request, so a filter chosen on one page can follow a link to another.
export type Scope = {
  site?: string
  date?: string
  date_from?: string
  date_to?: string
  camera?: string
  rig?: number
  telescope?: string
  filter?: string
  collection?: number
  project?: number
  dataset?: number
  target?: string
  q?: string
}

const TEXT = ['site', 'date', 'date_from', 'date_to', 'camera', 'telescope', 'filter', 'target', 'q'] as const
const IDS = ['rig', 'collection', 'project', 'dataset'] as const
const DAY = /^\d{4}-\d{2}-\d{2}$/

/** The scope part of a page's search params, cleaned: unknown keys dropped, ids as numbers, dates as dates. */
export function readScope(q: Record<string, unknown>): Scope {
  const out: Scope = {}
  for (const k of TEXT) {
    const v = q[k]
    if (typeof v !== 'string' && typeof v !== 'number') continue
    const s = String(v).trim()
    if (!s) continue
    if (k.startsWith('date') && !DAY.test(s)) continue
    out[k] = s
  }
  for (const k of IDS) {
    const n = Number(q[k])
    if (q[k] != null && q[k] !== '' && Number.isInteger(n) && n > 0) out[k] = n
  }
  return out
}

/** For a request's query string or a link's search: only what's set. */
export function scopeQuery(s: Scope): Record<string, string | number> {
  return Object.fromEntries(Object.entries(s).filter(([, v]) => v !== undefined && v !== '')) as Record<
    string,
    string | number
  >
}

export function scopeParams(s: Scope): string {
  return new URLSearchParams(Object.entries(scopeQuery(s)).map(([k, v]) => [k, String(v)])).toString()
}

export function isEmpty(s: Scope) {
  return Object.keys(scopeQuery(s)).length === 0
}
