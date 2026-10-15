import { describe, expect, it } from 'vitest'
import { locate, position, sequence } from './sequence'

const nights = [
  { first: '2026-02-24T20:00:00Z', last: '2026-02-24T23:00:00Z' },
  { first: '2026-04-24T21:00:00Z', last: '2026-04-25T01:00:00Z' },
]

describe('nights played end to end', () => {
  it('joins the nights, skipping the days between', () => {
    const s = sequence(nights)
    expect(s.total).toBe(7 * 3_600_000)
    expect(locate(s, 0)).toEqual({ night: 0, t: Date.parse(nights[0].first) })
    expect(locate(s, 3 * 3_600_000 + 1)).toEqual({ night: 1, t: Date.parse(nights[1].first) + 1 })
    expect(locate(s, s.total)).toEqual({ night: 1, t: Date.parse(nights[1].last) })
  })
  it('goes back and forth between real time and the joined clock', () => {
    const s = sequence(nights)
    const t = Date.parse('2026-04-24T23:30:00Z')
    expect(locate(s, position(s, 1, t))).toEqual({ night: 1, t })
  })
})
