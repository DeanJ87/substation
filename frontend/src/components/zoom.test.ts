import { describe, expect, it } from 'vitest'
import { anchoredScroll, clampZoom, fitScale, MAX_ZOOM } from './zoom'

describe('close look zoom', () => {
  it('fits the whole image, never past 100%, and is 100% until sizes are known', () => {
    expect(fitScale({ w: 1000, h: 800 }, { w: 4000, h: 2000 })).toBe(0.25)
    expect(fitScale({ w: 1000, h: 800 }, { w: 2000, h: 3200 })).toBe(0.25)
    expect(fitScale({ w: 1000, h: 800 }, { w: 500, h: 400 })).toBe(1)
    expect(fitScale(null, { w: 500, h: 400 })).toBe(1)
  })
  it('stops at fit going out and at the maximum going in', () => {
    expect(clampZoom(0.1, 0.25)).toBe(0.25)
    expect(clampZoom(0.5, 0.25)).toBe(0.5)
    expect(clampZoom(50, 0.25)).toBe(MAX_ZOOM)
    expect(clampZoom(0.5, 1)).toBe(1) // a small image never shrinks below 100%
  })
  it('keeps the point under the pointer still', () => {
    // at 100%, scrolled 200 and pointing 100 in: image x = 300; at 200% that point is at 600, so scroll 500
    expect(anchoredScroll(200, 100, 1, 2)).toBe(500)
    expect(anchoredScroll(500, 100, 2, 1)).toBe(200)
  })
})
