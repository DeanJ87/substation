import { describe, expect, it } from 'vitest'
import { isEmpty, readScope, scopeParams } from './scope'

describe('scope (spec 018)', () => {
  it('keeps what it understands, cleaned', () => {
    expect(
      readScope({
        rig: '3',
        filter: ' Ha ',
        date_from: '2026-02-01',
        date_to: 'soon',
        tab: 'x',
        collection: '0',
      }),
    ).toEqual({ rig: 3, filter: 'Ha', date_from: '2026-02-01' })
  })
  it('writes only what is set', () => {
    expect(scopeParams({ rig: 3, filter: 'Ha', date_to: undefined })).toBe('rig=3&filter=Ha')
    expect(isEmpty({ filter: '' })).toBe(true)
  })
})
