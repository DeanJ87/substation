import { describe, expect, it } from 'vitest'
import { besidesNights, isoDay, mapQuery, mapSearch, nearest, periodText, presets } from './search'

describe('the map address', () => {
  it('keeps a place, a zoom and a night', () => {
    expect(mapSearch({ lat: '54.995', lon: '-1.663', zoom: '12', date: '2026-10-11' })).toEqual({
      lat: 54.995,
      lon: -1.663,
      zoom: 12,
      date: '2026-10-11',
    })
  })

  it('drops half a place, out-of-range values and malformed dates', () => {
    const s = mapSearch({ lat: '54', zoom: '40', from: 'yesterday', to: '2026-10-15' })
    expect(s.lat).toBeUndefined()
    expect(s.lon).toBeUndefined()
    expect(s.zoom).toBeUndefined()
    expect(s.date_from).toBeUndefined()
    expect(s.date_to).toBe('2026-10-15') // `to`: the older name
  })

  it('lets one night win over a range', () => {
    const s = mapSearch({ date: '2026-10-11', date_from: '2026-10-01', to: '2026-10-31' })
    expect(mapQuery(s)).toEqual({ date: '2026-10-11' })
    expect(mapQuery(mapSearch({ from: '2026-10-01' }))).toEqual({ date_from: '2026-10-01' })
  })

  it('asks for the whole scope but never the view (spec 018)', () => {
    const s = mapSearch({
      lat: '54.9',
      lon: '-1.6',
      zoom: '9',
      rig: '3',
      collection: '7',
      date_to: '2026-10-01',
    })
    expect(mapQuery(s)).toEqual({ rig: 3, collection: 7, date_to: '2026-10-01' })
    expect(besidesNights(s)).toEqual({ rig: 3, collection: 7 })
  })

  it('says which nights it shows', () => {
    expect(periodText({})).toBeNull()
    expect(periodText({ date: '2026-10-11' })).toBe('11 Oct 2026')
    expect(periodText({ date_from: '2026-10-01', date_to: '2026-10-15' })).toBe('1 Oct 2026 to 15 Oct 2026')
    expect(periodText({ date_from: '2026-10-01' })).toBe('from 1 Oct 2026')
    expect(periodText({ date_to: '2026-10-01' })).toBe('up to 1 Oct 2026')
  })

  it('offers the last 30 days, this month and this year', () => {
    const p = presets(new Date(2026, 9, 15))
    expect(p.map((x) => x.label)).toEqual(['Last 30 days', 'This month', 'This year'])
    expect(p[0].search).toEqual({ date_from: '2026-09-15', date_to: '2026-10-15' })
    expect(p[1].search.date_from).toBe('2026-10-01')
    expect(p[2].search.date_from).toBe('2026-01-01')
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
