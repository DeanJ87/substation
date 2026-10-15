import { describe, expect, it } from 'vitest'
import {
  agoText,
  bytes,
  durationText,
  fileName,
  integrationText,
  nightText,
  shortDateText,
  signed,
  temp,
  timeText,
} from './format'

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

describe('more formats', () => {
  it('names nights and times', () => {
    expect(nightText('2026-10-03')).toBe('3 October 2026')
    expect(nightText(null)).toBe('no night')
    expect(timeText(null)).toBe('—')
    expect(timeText('2026-10-03T21:05:09')).toBe('21:05:09')
    expect(fileName('/a/b/c.fit')).toBe('c.fit')
  })
  it('scales bytes and says how long ago', () => {
    expect(bytes(512)).toEqual({ value: '512', unit: 'B' })
    expect(bytes(48_211_234)).toEqual({ value: '48.2', unit: 'MB' })
    expect(bytes(2e15)).toEqual({ value: '2000', unit: 'TB' })
    const now = Date.parse('2026-10-03T12:00:00Z')
    expect(agoText(null, now)).toBe('—')
    expect(agoText('2026-10-03T11:59:30Z', now)).toBe('just now')
    expect(agoText('2026-10-03T11:48:00Z', now)).toBe('12 min ago')
    expect(agoText('2026-10-03T09:00:00Z', now)).toBe('3 h ago')
    expect(agoText('2026-10-02T12:00:00Z', now)).toBe('1 day ago')
    expect(agoText('2026-09-30T12:00:00Z', now)).toBe('3 days ago')
  })
  it('writes long durations and short integrations', () => {
    expect(durationText(null)).toBe('—')
    expect(durationText(90000)).toBe('1 day 1 h')
    expect(durationText(3 * 86400)).toBe('3 days 0 h')
    expect(integrationText(600)).toBe('10m')
    expect(shortDateText(null)).toBe('—')
  })
})
