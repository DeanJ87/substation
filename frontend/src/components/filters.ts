// Filters, one table (007-DR-38): how a filter is named, ordered and coloured everywhere it appears. The names
// come in many spellings from headers (Ha, Halpha, H-alpha, O3, S2…); the app shows the canonical one.

export type FilterKey = 'l' | 'r' | 'g' | 'b' | 'ha' | 'oiii' | 'sii' | 'osc'

const TABLE: { key: FilterKey; name: string; re: RegExp }[] = [
  { key: 'l', name: 'L', re: /^(l|lum|luminance|clear)$/ },
  { key: 'r', name: 'R', re: /^(r|red)$/ },
  { key: 'g', name: 'G', re: /^(g|green)$/ },
  { key: 'b', name: 'B', re: /^(b|blue)$/ },
  { key: 'ha', name: 'Hα', re: /^(ha|hα|h-?alpha|halpha2?|hα2|ha2)$/ },
  { key: 'oiii', name: 'OIII', re: /^(oiii|o3|o-iii)$/ },
  { key: 'sii', name: 'SII', re: /^(sii|s2|s-ii)$/ },
  { key: 'osc', name: 'OSC', re: /^(osc|rgb|colou?r|none|no ?filter)$/ },
]

const squash = (f: string) => f.trim().toLowerCase().replace(/\s+/g, '')

/** The filter's family, or null for a name we don't know. */
export function filterKey(filter: string | null | undefined): FilterKey | null {
  const f = squash(filter ?? '')
  if (!f) return null
  return TABLE.find((t) => t.re.test(f))?.key ?? null
}

/** The name to show: "Halpha" → "Hα", "O3" → "OIII". Unknown names are shown as they are. */
export function filterName(filter: string | null | undefined): string {
  const k = filterKey(filter)
  if (!k) return (filter ?? '').trim()
  return TABLE.find((t) => t.key === k)!.name
}

/** The filter's colour token. OSC and unknown filters get the neutral one. */
export function filterColour(filter: string | null | undefined): string {
  const k = filterKey(filter)
  return k && k !== 'osc' ? `var(--sst-filter-${k})` : 'var(--sst-filter-other)'
}

/** The canonical order: L R G B, Hα OIII SII, OSC, then anything else by name. */
export function filterRank(filter: string | null | undefined): number {
  const k = filterKey(filter)
  const i = k ? TABLE.findIndex((t) => t.key === k) : -1
  return i < 0 ? TABLE.length : i
}

export function compareFilters(a: string | null | undefined, b: string | null | undefined): number {
  return filterRank(a) - filterRank(b) || (a ?? '').localeCompare(b ?? '', 'en-GB', { numeric: true })
}

/** Sort anything by its filter in the canonical order. */
export function byFilter<T>(rows: T[], get: (row: T) => string | null | undefined): T[] {
  return [...rows].sort((x, y) => compareFilters(get(x), get(y)))
}

export function sortFilters(filters: string[]): string[] {
  return [...filters].sort(compareFilters)
}
