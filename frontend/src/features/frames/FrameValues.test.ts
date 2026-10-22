import { describe, expect, it } from 'vitest'
import { sourceText } from './FrameValues'

const base = { field: 'filter', value: 'Hα', raw: 'Ha', is_winner: true, at: '2026-10-09T20:00:00Z' }

describe('sourceText', () => {
  it('names the header keyword', () => {
    expect(sourceText({ ...base, source: 'header', source_detail: 'FILTER', set_by: null })).toBe(
      'from header FILTER',
    )
  })
  it('names the pattern', () => {
    expect(
      sourceText({ ...base, source: 'filename_pattern', source_detail: 'pattern #3', set_by: null }),
    ).toBe('from file name pattern #3')
    expect(sourceText({ ...base, source: 'folder_pattern', source_detail: 'pattern #1', set_by: null })).toBe(
      'from folder pattern #1',
    )
  })
  it('names who set it and when', () => {
    expect(sourceText({ ...base, source: 'user', source_detail: null, set_by: 'dean' })).toBe(
      'set by dean on 9 Oct 2026',
    )
  })
})
