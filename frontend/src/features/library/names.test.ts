import { describe, expect, it } from 'vitest'
import { collectionFacts, nameParts, otherObjects } from './names'

describe('collection names', () => {
  it('splits a designation from the common name', () => {
    expect(nameParts('NGC 7635 - Bubble Nebula')).toEqual({ title: 'Bubble Nebula', designation: 'NGC 7635' })
    expect(nameParts('M 17')).toEqual({ title: 'M 17', designation: '' })
  })
  it("doesn't repeat what the title says", () => {
    expect(
      collectionFacts({
        name: 'NGC 7635 - Bubble Nebula',
        objects: 'NGC 7635',
        constellation: 'Cassiopeia',
        datasets: 2,
      }),
    ).toBe('Cassiopeia · 2 datasets')
    expect(otherObjects("M 81 - Bode's Galaxy", "M81 - Bode's Galaxy")).toEqual([])
    expect(otherObjects('NGC 7822 - Question Mark Nebula', 'NGC7822')).toEqual([])
  })
  it('keeps other objects in the frame', () => {
    expect(otherObjects('NGC 6960 - Veil Nebula', 'HD 335226 · NGC 6960 · NGC 6992')).toEqual([
      'HD 335226',
      'NGC 6992',
    ])
  })
})
