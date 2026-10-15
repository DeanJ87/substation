import { describe, expect, it } from 'vitest'
import { R, at, azAt, compass, hourTicks, marker, polyline, project, ring, series } from './projection'

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
