// A filter's tint token: L, R, G, B, Hα, OIII, SII from the one filter table (filters.ts). Colour filters (OSC,
// RGB) and unknown names get none: their pictures carry their own colour.
import { filterKey } from './filters'

export function filterTint(filter: string | null | undefined): string | null {
  const k = filterKey(filter)
  return k && k !== 'osc' ? `var(--sst-filter-${k})` : null
}

/** The filter at the end of a dataset label ("Askar 71F + ATR2600M · OIII · Panel 1" → OIII). */
export function filterOfLabel(label: string): string {
  const parts = label.split(' · ').map((x) => x.trim())
  return parts.find((p) => filterTint(p)) ?? ''
}
