import { describe, expect, it } from 'vitest'
import { bytes, durationText, integrationText, shortDateText, signed, temp } from './format'

describe('writing rules (007-DR-14)', () => {
  it('uses a real minus sign, en-GB grouping and a dash for missing values', () => {
    expect(signed(-20)).toBe('−20')
    expect(signed(1234.5, 1, true)).toBe('+1,234.5')
    expect(signed(null)).toBe('—')
    expect(temp(-19.9)).toBe('−19.9 °C')
    expect(bytes(null).value).toBe('—')
  })
  it('writes dates and durations as people say them', () => {
    expect(shortDateText('2026-10-03')).toBe('3 Oct 2026')
    expect(durationText(45)).toBe('45 s')
    expect(durationText(720)).toBe('12 min')
    expect(durationText(3900)).toBe('1 h 05 min')
    expect(integrationText(37800)).toBe('10h 30m')
  })
})
