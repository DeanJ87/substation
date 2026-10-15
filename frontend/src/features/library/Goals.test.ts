import { describe, expect, it } from 'vitest'
import type { components } from '../../api/schema'
import { goalProgress } from './Goals'

type Card = components['schemas']['CollectionCard']
const card = {
  filters: { L: 3600 },
  filter_time: { L: { total_s: 10800, accepted_s: 3600, rejected_s: 1800 } },
  goals: { L: 4, Ha: 10 },
} as unknown as Card

describe('goal progress (spec 019)', () => {
  it('counts kept integration against the goal, waiting apart', () => {
    expect(goalProgress(card, 'L')).toEqual({ kept: 3600, waiting: 5400, goal: 14400, pct: 25 })
  })
  it('a filter not shot yet is at nothing', () => {
    expect(goalProgress(card, 'Ha')).toEqual({ kept: 0, waiting: 0, goal: 36000, pct: 0 })
  })
})
