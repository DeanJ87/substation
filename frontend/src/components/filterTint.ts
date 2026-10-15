// A filter's tint token (2026-10-16): L white, R red, G green, B blue, Hα deep red, OIII teal, SII amber. Colour
// filters (OSC, RGB) and unknown names get none: their pictures carry their own colour.
const TINTS: [RegExp, string][] = [
  [/^(l|lum|luminance|clear)$/, 'l'],
  [/^(r|red)$/, 'r'],
  [/^(g|green)$/, 'g'],
  [/^(b|blue)$/, 'b'],
  [/^(ha|hα|h-?alpha|halpha2?|hα2|ha2)$/, 'ha'],
  [/^(oiii|o3|o-iii)$/, 'oiii'],
  [/^(sii|s2|s-ii)$/, 'sii'],
]

export function filterTint(filter: string | null | undefined): string | null {
  const f = (filter ?? '').trim().toLowerCase().replace(/\s+/g, '')
  for (const [re, key] of TINTS) if (re.test(f)) return `var(--sst-filter-${key})`
  return null
}

/** The filter at the end of a dataset label ("Askar 71F + ATR2600M · OIII · Panel 1" → OIII). */
export function filterOfLabel(label: string): string {
  const parts = label.split(' · ').map((x) => x.trim())
  return parts.find((p) => filterTint(p)) ?? ''
}
