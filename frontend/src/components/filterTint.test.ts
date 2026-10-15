import { describe, expect, it } from 'vitest'
import { filterOfLabel, filterTint } from './filterTint'

describe('filter tints', () => {
  it('knows the usual names', () => {
    expect(filterTint('L')).toBe('var(--sst-filter-l)')
    expect(filterTint('Hα')).toBe('var(--sst-filter-ha)')
    expect(filterTint('H-alpha')).toBe('var(--sst-filter-ha)')
    expect(filterTint('OIII')).toBe('var(--sst-filter-oiii)')
    expect(filterTint('S2')).toBe('var(--sst-filter-sii)')
    expect(filterTint('OSC')).toBeNull()
    expect(filterTint('')).toBeNull()
  })
  it('finds the filter in a dataset label', () => {
    expect(filterOfLabel('Askar 71F + ATR2600M · OIII · Panel 1')).toBe('OIII')
  })
})
