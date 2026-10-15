import { describe, expect, it } from 'vitest'
import { isoDay, mapSearch, nearest, period, periodText, presets } from './search'

describe('the map address', () => {
  it('keeps a place, a zoom and a night', () => {
    expect(mapSearch({ lat: '54.995', lon: '-1.663', zoom: '12', date: '2026-10-11' })).toEqual({
      lat: 54.995,
      lon: -1.663,
      zoom: 12,
      date: '2026-10-11',
      from: undefined,
      to: undefined,
    })
  })

  it('drops half a place, out-of-range values and malformed dates', () => {
    const s = mapSearch({ lat: '54', zoom: '40', from: 'yesterday', to: '2026-10-15' })
    expect(s.lat).toBeUndefined()
    expect(s.lon).toBeUndefined()
    expect(s.zoom).toBeUndefined()
    expect(s.from).toBeUndefined()
    expect(s.to).toBe('2026-10-15')
  })

  it('lets one night win over a range', () => {
    const s = mapSearch({ date: '2026-10-11', from: '2026-10-01', to: '2026-10-31' })
    expect(period(s)).toEqual({ since: '2026-10-11', until: '2026-10-11' })
    expect(period(mapSearch({ from: '2026-10-01' }))).toEqual({ since: '2026-10-01', until: undefined })
  })

  it('says which nights it shows', () => {
    expect(periodText({})).toBeNull()
    expect(periodText({ date: '2026-10-11' })).toBe('11 Oct 2026')
    expect(periodText({ from: '2026-10-01', to: '2026-10-15' })).toBe('1 Oct 2026 to 15 Oct 2026')
    expect(periodText({ from: '2026-10-01' })).toBe('from 1 Oct 2026')
    expect(periodText({ to: '2026-10-01' })).toBe('up to 1 Oct 2026')
  })

  it('offers the last 30 days, this month and this year', () => {
    const p = presets(new Date(2026, 9, 15))
    expect(p.map((x) => x.label)).toEqual(['Last 30 days', 'This month', 'This year'])
    expect(p[0].search).toEqual({ from: '2026-09-15', to: '2026-10-15' })
    expect(p[1].search.from).toBe('2026-10-01')
    expect(p[2].search.from).toBe('2026-01-01')
    expect(isoDay(new Date(2026, 0, 5))).toBe('2026-01-05')
  })

  it('finds the place a night page points at, within a few kilometres', () => {
    const places = [
      { key: 'home', lat: 54.995, lon: -1.663 },
      { key: 'away', lat: -8.496, lon: 119.887 },
    ]
    expect(nearest(places, 54.9951, -1.6634)?.key).toBe('home')
    expect(nearest(places, 51.5, -0.12)).toBeNull()
  })
})
