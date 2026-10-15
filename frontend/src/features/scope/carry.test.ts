import { describe, expect, it } from 'vitest'
import { mapSearch } from '../map/search'
import { forNight, inNights, omit, readScope, replaceScope, scopeQuery } from './scope'

// spec 018 FR-004: a scope chosen on one page follows the links to the next
describe('carrying the scope from page to page', () => {
  const library = readScope({ q: 'M 81', rig: '3', date_from: '2026-02-01', date_to: '2026-02-28' })

  it('keeps a page’s own keys when its scope changes', () => {
    const search = { tab: 'sessions', nights: '2026-02-03', rig: 2, filter: 'Ha' }
    expect(replaceScope(search, { rig: 3 })).toEqual({ tab: 'sessions', nights: '2026-02-03', rig: 3 })
    expect(replaceScope({ sub: 'abc', q: 'x' }, {})).toEqual({ sub: 'abc' })
  })

  it('Library → collection → map: the map reads the same scope, with its collection', () => {
    const toMap = { ...scopeQuery(omit(library, 'collection')), collection: 7 }
    expect(readScope(mapSearch(toMap))).toEqual({ ...library, collection: 7 })
  })

  it('map → night → What to shoot: that night and place instead of the range', () => {
    const atNight = readScope({ ...scopeQuery(library), collection: 7, site: '54.99,-1.66' })
    expect(forNight(atNight, '2026-02-03', '54.99,-1.66')).toEqual({
      rig: 3,
      collection: 7,
      date: '2026-02-03',
      site: '54.99,-1.66',
    })
    expect(forNight({}, '2026-02-03')).toEqual({ date: '2026-02-03' })
  })

  it('says whether a night is within the scope', () => {
    expect(inNights({}, null)).toBe(true)
    expect(inNights(library, '2026-02-03')).toBe(true)
    expect(inNights(library, '2026-03-01')).toBe(false)
    expect(inNights(library, undefined)).toBe(false)
    expect(inNights({ date: '2026-02-03' }, '2026-02-03')).toBe(true)
    expect(inNights({ date_to: '2026-02-01' }, '2026-02-03')).toBe(false)
  })
})
