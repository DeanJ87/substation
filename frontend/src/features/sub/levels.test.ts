import { describe, expect, it } from 'vitest'
import { gammaOf, isNeutral, levelOut, NEUTRAL, signed, tableValues } from './levels'

describe('display levels curve (012-DR-08)', () => {
  it('is the identity when neutral', () => {
    for (const v of [0, 1, 64, 128, 254, 255]) expect(levelOut(v, NEUTRAL)).toBeCloseTo(v, 9)
    expect(isNeutral(NEUTRAL)).toBe(true)
  })
  it('maps the black point to black and stretches the rest to white', () => {
    const l = { black: 40, bright: 0 }
    expect(levelOut(0, l)).toBe(0)
    expect(levelOut(40, l)).toBe(0)
    expect(levelOut(255, l)).toBe(255)
    // out = (in − b) / (255 − b) on the 0–255 scale
    expect(levelOut(100, l)).toBeCloseTo((255 * 60) / 215, 9)
  })
  it('lifts the shadows with a negative black point', () => {
    const l = { black: -20, bright: 0 }
    expect(levelOut(0, l)).toBeCloseTo((255 * 20) / 275, 9)
    expect(levelOut(255, l)).toBe(255)
  })
  it('applies the brightness as a gamma after the black point', () => {
    expect(gammaOf(0)).toBe(1)
    expect(gammaOf(50)).toBeCloseTo(0.5)
    expect(gammaOf(-50)).toBeCloseTo(2)
    const l = { black: 30, bright: 50 }
    expect(levelOut(130, l)).toBeCloseTo(255 * (100 / 225) ** 0.5, 9)
    expect(levelOut(130, l)).toBeGreaterThan(levelOut(130, { black: 30, bright: 0 }))
  })
  it('clamps out-of-range settings', () => {
    expect(levelOut(200, { black: 999, bright: 0 })).toBe(levelOut(200, { black: 128, bright: 0 }))
  })
  it('gives the SVG filter one entry per 8-bit value', () => {
    const t = tableValues({ black: 64, bright: 0 }).split(' ').map(Number)
    expect(t).toHaveLength(256)
    expect(t[0]).toBe(0)
    expect(t[64]).toBe(0)
    expect(t[255]).toBe(1)
    expect(t[128]).toBeCloseTo(64 / 191, 4)
  })
  it('writes values with their sign', () => {
    expect(signed(12)).toBe('+12')
    expect(signed(-4)).toBe('−4')
    expect(signed(0)).toBe('0')
  })
})
