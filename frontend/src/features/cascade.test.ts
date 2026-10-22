import { describe, expect, it } from 'vitest'
import { inRange, keepIfOffered, keepOffered, setRangeEnd, todayIso } from './cascade'
import { filterOptions } from './scope/ScopeBar'
import { hasDestination } from './settings/Sections'
import { roleChange, roleFilterChoices } from './finished/FinishedProject'
import { goalExtras, panelsApply, splitOptions } from './library/ProjectCards'
import { whereOptions } from './library/Library'

describe('dependent fields (018-DR-17)', () => {
  it('keeps a child only while its parent still offers it', () => {
    expect(keepIfOffered('Hα', ['Hα', 'OIII'])).toBe('Hα')
    expect(keepIfOffered('SII', ['Hα', 'OIII'])).toBeUndefined()
    expect(keepOffered(['b', 'x', 'a'], ['a', 'b'])).toEqual(['b', 'a'])
  })
  it('never lets a date range turn inside out', () => {
    expect(setRangeEnd({ from: '2026-01-01', to: '2026-02-01' }, 'from', '2026-03-01')).toEqual({
      from: '2026-03-01',
      to: '2026-03-01',
    })
    expect(setRangeEnd({ from: '2026-03-01', to: '2026-04-01' }, 'to', '2026-02-01')).toEqual({
      from: '2026-02-01',
      to: '2026-02-01',
    })
    expect(setRangeEnd({ from: '2026-03-01' }, 'from', '')).toEqual({ from: undefined })
    expect(inRange('2026-03-05', { from: '2026-03-01' })).toBe(true)
    expect(inRange('2026-02-05', { from: '2026-03-01' })).toBe(false)
    expect(todayIso(new Date(2026, 9, 2))).toBe('2026-10-02')
  })
  it('says when a linked filter is not on the chosen rig, and does not offer it again', () => {
    expect(filterOptions(['Hα', 'SII'], ['Hα'], 'SII')).toEqual([
      { value: 'Hα', label: 'Hα' },
      { value: 'SII', label: 'SII (none on this rig)', disabled: true },
    ])
    expect(filterOptions(['Hα'], undefined, undefined)).toEqual([{ value: 'Hα', label: 'Hα' }])
  })
  it('offers a test notification only with somewhere to send it', () => {
    expect(hasDestination({ ntfy: '', webhook: '' })).toBe(false)
    expect(hasDestination({ ntfy: '', webhook: '', pushover_user: 'u', pushover_token: '' })).toBe(false)
    expect(hasDestination({ ntfy: 'https://ntfy.sh/x', webhook: '' })).toBe(true)
  })
  it("offers a finished image the linked collections' filters, and clears what the old role had", () => {
    expect(roleFilterChoices(['OIII', 'Ha'], null)).toEqual(['Hα', 'OIII'])
    expect(roleFilterChoices([], null)).toEqual(['L', 'R', 'G', 'B', 'Hα', 'OIII', 'SII'])
    expect(roleFilterChoices(['OIII'], 'Duo')).toEqual(['OIII', 'Duo'])
    const cur = { role: 'per_filter', role_filter: 'Hα', role_order: null, role_label: '' }
    expect(roleChange('final', cur, () => 1)).toEqual({
      role: 'final',
      role_filter: '',
      role_order: null,
      role_label: '',
    })
    expect(roleChange('step', cur, () => 3).role_order).toBe(3)
  })
  it("offers goals for the project's rigs' filters it has no goal for", () => {
    expect(goalExtras(['Hα'], ['Ha', 'OIII', 'SII'])).toEqual(['OIII', 'SII'])
    expect(goalExtras(['L'], [])).toContain('OSC')
  })
  it('offers only the splits that make two projects', () => {
    const ways = splitOptions({ rigs: ['A'], panels: [1, 2], dataset_ids: [1, 2] })
    expect(ways.map((w) => [w.value, w.disabled])).toEqual([
      ['rig', true],
      ['panel', false],
      ['datasets', false],
    ])
    expect(panelsApply('single', 'mosaic')).toBe(false)
    expect(panelsApply('auto', 'mosaic')).toBe(true)
  })
  it('counts each Files choice and disables the empty ones', () => {
    const cards = [
      { files_where: 'active', archive_suggested: false },
      { files_where: 'active', archive_suggested: true },
    ] as never[]
    const opts = whereOptions(cards, '')
    expect(opts.find((o) => o.value === 'active')).toMatchObject({ label: 'In the active library (2)' })
    expect(opts.find((o) => o.value === 'archive')).toMatchObject({ disabled: true })
    expect(whereOptions(cards, 'archive').find((o) => o.value === 'archive')?.disabled).toBe(false)
  })
})
