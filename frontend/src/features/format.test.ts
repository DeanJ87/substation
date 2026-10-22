import { describe, expect, it } from 'vitest'
import {
  agoText,
  angleText,
  binText,
  bytes,
  bytesText,
  clockText,
  dateText,
  dateTimeText,
  durationText,
  exposureText,
  fileName,
  integrationText,
  monthSpan,
  nightShort,
  nightText,
  numText,
  pctText,
  plural,
  shortDateText,
  signed,
  temp,
  timeText,
} from './format'

describe('writing rules (007-DR-14, 007-DR-39)', () => {
  it('uses a real minus sign, en-GB grouping and a dash for missing values', () => {
    expect(signed(-20)).toBe('−20')
    expect(signed(1234.5, 1, true)).toBe('+1,234.5')
    expect(signed(null)).toBe('—')
    expect(numText(-83)).toBe('−83')
    expect(numText(1390)).toBe('1,390')
    expect(numText(-0.01, 1)).toBe('0.0')
    expect(temp(-19.9)).toBe('−19.9 °C')
    expect(bytes(null).value).toBe('—')
  })
  it('writes one date style, never "Sept"', () => {
    expect(dateText('2026-09-18')).toBe('18 Sep 2026')
    expect(shortDateText('2026-10-03')).toBe('3 Oct 2026')
    expect(nightText('2026-10-03')).toBe('3 Oct 2026')
    expect(nightText(null)).toBe('no night')
    expect(nightShort('2026-09-18')).toBe('18 Sep')
    expect(monthSpan('2026-09-18', '2026-09-30')).toBe('Sep 2026')
    expect(monthSpan('2025-10-01', '2026-01-02')).toBe('Oct 2025 to Jan 2026')
    expect(dateTimeText('2026-09-18T21:12:40')).toBe('18 Sep 2026, 21:12')
  })
  it('writes times to the minute', () => {
    expect(timeText(null)).toBe('—')
    expect(timeText('2026-10-03T21:05:09')).toBe('21:05')
    expect(clockText('2026-10-03T07:45:00')).toBe('07:45')
  })
  it('writes one compact duration style', () => {
    expect(integrationText(37800)).toBe('10h 30m')
    expect(integrationText(18000)).toBe('5h')
    expect(integrationText(3900)).toBe('1h 05m')
    expect(integrationText(600)).toBe('10m')
    expect(durationText(45)).toBe('45s')
    expect(durationText(720)).toBe('12m')
    expect(durationText(3900)).toBe('1h 05m')
    expect(durationText(90000)).toBe('1d 1h')
    expect(durationText(3 * 86400)).toBe('3d')
    expect(durationText(null)).toBe('—')
  })
  it('writes exposures, angles, binning and percentages', () => {
    expect(exposureText(300)).toBe('300 s')
    expect(exposureText(2.5)).toBe('2.5 s')
    expect(exposureText(0.001)).toBe('1 ms')
    expect(angleText(-9)).toBe('−9°')
    expect(binText(1)).toBe('1×1')
    expect(binText('2x2')).toBe('2×2')
    expect(pctText(0.5)).toBe('50%')
    expect(plural(1, 'sub')).toBe('1 sub')
    expect(plural(1390, 'sub')).toBe('1,390 subs')
  })
})

describe('more formats', () => {
  it('scales bytes and says how long ago', () => {
    expect(bytes(512)).toEqual({ value: '512', unit: 'B' })
    expect(bytes(48_211_234)).toEqual({ value: '48.2', unit: 'MB' })
    expect(bytes(2e15)).toEqual({ value: '2000', unit: 'TB' })
    expect(bytesText(20_800_000_000)).toBe('20.8 GB')
    const now = Date.parse('2026-10-03T12:00:00Z')
    expect(agoText(null, now)).toBe('—')
    expect(agoText('2026-10-03T11:59:30Z', now)).toBe('just now')
    expect(agoText('2026-10-03T11:48:00Z', now)).toBe('12m ago')
    expect(agoText('2026-10-03T09:00:00Z', now)).toBe('3h ago')
    expect(agoText('2026-10-02T12:00:00Z', now)).toBe('1 day ago')
    expect(agoText('2026-09-30T12:00:00Z', now)).toBe('3 days ago')
    expect(fileName('/a/b/c.fit')).toBe('c.fit')
  })
})
