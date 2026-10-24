// The Settings example draws subs with the same maths as the server's previews (003 amendment 2026-10-24).
import { describe, expect, it } from 'vitest'
import { draw, drawPair, sampleSub, sharedParams, stretchParams } from './previewLook'

const mean = (a: Uint8ClampedArray) => a.reduce((t, x) => t + x, 0) / a.length

describe('preview look', () => {
  it('moves the black point by noise sigmas, darker when raised', () => {
    const sky = sampleSub(1)
    const [lo0] = stretchParams(sky)
    const [loUp] = stretchParams(sky, 1)
    expect(loUp).toBeGreaterThan(lo0)
    expect(mean(draw(sky, stretchParams(sky, 2)))).toBeLessThan(mean(draw(sky, stretchParams(sky, -2))))
  })

  it('shares one stretch per session, so a cloudy sub shows darker; per sub it looks like the rest', () => {
    const look = { black_point: 0, background: 0.25 }
    const [clearS, cloudyS] = drawPair({ mode: 'session', ...look })
    expect(mean(cloudyS)).toBeLessThan(mean(clearS) - 15)
    const [clearP, cloudyP] = drawPair({ mode: 'sub', ...look })
    expect(Math.abs(mean(cloudyP) - mean(clearP))).toBeLessThan(mean(clearS) - mean(cloudyS))
  })

  it('takes the median of each parameter', () => {
    expect(
      sharedParams([
        [1, 0.1, 10],
        [2, 0.2, 20],
        [9, 0.9, 90],
      ]),
    ).toEqual([2, 0.2, 20])
  })
})
