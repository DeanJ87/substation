import { describe, expect, it } from 'vitest'
import {
  R,
  altRing,
  at,
  azAt,
  compass,
  hourTicks,
  marker,
  polyline,
  project,
  project3d,
  ring,
  series,
  skyLine,
} from './projection'

describe('the dome projection', () => {
  it('puts the zenith in the middle and the horizon on the edge', () => {
    expect(Math.hypot(...Object.values(project(90, 123)))).toBe(0)
    const north = project(0, 0)
    expect(north.x).toBeCloseTo(0)
    expect(north.y).toBeCloseTo(-R)
    expect(Math.hypot(...Object.values(project(0, 217)))).toBeCloseTo(R, 1)
  })

  it('looks up: north at the top, east on the left, south at the bottom, west on the right', () => {
    expect(project(0, 90).x).toBeCloseTo(-R)
    expect(project(0, 180).y).toBeCloseTo(R)
    expect(project(0, 270).x).toBeCloseTo(R)
  })

  it('spaces altitude evenly, so 30° and 60° rings divide the dome in thirds', () => {
    expect(ring(60)).toBeCloseTo(R / 3)
    expect(ring(30)).toBeCloseTo((2 * R) / 3)
    expect(Math.hypot(...Object.values(project(45, 45)))).toBeCloseTo(R / 2, 1)
  })

  it('labels the compass just outside the horizon', () => {
    const labels = compass()
    expect(labels.map((c) => c.label)).toEqual(['N', 'E', 'S', 'W'])
    for (const c of labels) expect(Math.hypot(c.at.x, c.at.y)).toBeGreaterThan(R)
  })
})

describe('marks and lines', () => {
  it('draws a path through points', () => {
    expect(
      polyline([
        { x: 0, y: 0 },
        { x: 1, y: 2 },
      ]),
    ).toBe('M0 0 L1 2')
  })

  it('makes a closed outline for every shape, centred on the point', () => {
    for (const shape of ['circle', 'square', 'triangle', 'diamond', 'cross'] as const) {
      const d = marker(shape, { x: 10, y: 20 }, 4)
      expect(d.startsWith('M')).toBe(true)
      expect(d.endsWith('Z')).toBe(true)
    }
  })

  it('cycles six series colours from the theme', () => {
    expect(series(0)).toBe('var(--sst-series-1)')
    expect(series(6)).toBe('var(--sst-series-1)')
    expect(series(5)).toBe('var(--sst-series-6)')
  })
})

describe('interpolating through the night', () => {
  const samples = [
    { time: '2026-10-11T21:00:00Z', alt: 10, az: 350 },
    { time: '2026-10-11T22:00:00Z', alt: 30, az: 10 },
  ]
  const mid = Date.parse('2026-10-11T21:30:00Z')

  it('finds a value between samples, and nothing outside them', () => {
    expect(at(samples, mid, (s) => s.alt)).toBe(20)
    expect(at(samples, Date.parse('2026-10-11T20:00:00Z'), (s) => s.alt)).toBeNull()
    expect(at([], mid, () => 1)).toBeNull()
  })

  it('goes the short way round through north', () => {
    expect(azAt(samples, mid)).toBeCloseTo(0)
  })

  it('ticks each hour in a span', () => {
    const t = hourTicks(Date.parse('2026-10-11T20:30:00Z'), Date.parse('2026-10-11T23:10:00Z'))
    expect(t.map((x) => new Date(x).toISOString().slice(11, 16))).toEqual(['21:00', '22:00', '23:00'])
  })
})

describe('the dome from the side', () => {
  it('stands behind you looking south: the zenith on top, the north rim nearest, the south rim far', () => {
    const z = project3d(90, 0)
    expect(z.x).toBeCloseTo(0)
    expect(z.y).toBeLessThan(-80)
    const south = project3d(0, 180)
    const north = project3d(0, 0)
    expect(north.y).toBeGreaterThan(0) // the near rim is low
    expect(south.y).toBeLessThan(0) // the far rim is high
    expect(north.front && !south.front).toBe(true)
  })
  it('has east on the left and west on the right, facing south', () => {
    expect(project3d(0, 90).x).toBeLessThan(0)
    expect(project3d(0, 270).x).toBeGreaterThan(0)
  })
  it('turns with the view', () => {
    const facingNorth = { yaw: 0, tilt: 32 }
    expect(project3d(0, 180, facingNorth).front).toBe(true)
    expect(project3d(0, 90, facingNorth).x).toBeGreaterThan(0) // east on the right facing north
  })
  it('splits a ring into its near and far halves', () => {
    const thirty = skyLine(altRing(30))
    expect(thirty.front).toMatch(/^M/)
    expect(thirty.back).toMatch(/^M/)
  })
})
