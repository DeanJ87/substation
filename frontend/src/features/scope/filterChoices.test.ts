import { describe, expect, it } from 'vitest'
import { filterChoices } from './ScopeBar'

describe('filter choices follow the rig', () => {
  it('offers only what the chosen rig shot through', () => {
    expect(filterChoices(['Hα', 'OIII', 'OSC'], ['Hα', 'OIII'], undefined)).toEqual(['Hα', 'OIII'])
  })
  it("offers the rig's own filters when the page names none", () => {
    expect(filterChoices([], ['OSC'], undefined)).toEqual(['OSC'])
  })
  it('offers everything without a rig, and keeps the current choice visible', () => {
    expect(filterChoices(['OIII', 'Hα'], undefined, 'SII')).toEqual(['Hα', 'OIII', 'SII'])
  })
})
