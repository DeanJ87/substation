import { describe, expect, it } from 'vitest'
import {
  R,
  altRing,
  at,
  azAt,
  compass,
  dragView,
  frameOnDome,
  frameOutline,
  fromTangent,
  homeFor,
  hourTicks,
  marker,
  polyline,
  project,
  project3d,
  ring,
  series,
  siderealDeg,
  skyLine,
  splitSides,
  surveyPixel,
  toEquatorial,
  toHorizontal,
  unproject,
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

describe('the dome seen from outside', () => {
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
  it('puts what you look towards on the far wall and what is behind you on the near shell', () => {
    for (const yaw of [0, 90, 180, 270, 33]) {
      const view = { yaw, tilt: 32 }
      expect(project3d(20, yaw, view).front).toBe(false) // ahead, low: the far wall
      expect(project3d(20, yaw + 180, view).front).toBe(true) // behind the dome's middle: the near shell
    }
    // seen from high above, the zenith faces you; from low down it's on the far wall
    expect(project3d(90, 0, { yaw: 180, tilt: 60 }).front).toBe(true)
    expect(project3d(60, 180, { yaw: 180, tilt: 10 }).front).toBe(false)
  })
  it('has the compass where it stands, seen from outside: looking north, east is on the right', () => {
    const north = { yaw: 0, tilt: 32 }
    expect(project3d(0, 90, north).x).toBeGreaterThan(project3d(0, 270, north).x)
    expect(project3d(0, 0, north).y).toBeLessThan(project3d(0, 180, north).y) // north at the back, higher up
    // looking south, east is on the left, as it is standing on the ground looking south
    const south = { yaw: 180, tilt: 32 }
    expect(project3d(0, 90, south).x).toBeLessThan(project3d(0, 270, south).x)
    // looking east, north is on the left
    const east = { yaw: 90, tilt: 32 }
    expect(project3d(0, 0, east).x).toBeLessThan(project3d(0, 180, east).x)
  })
  it('from straight above is the 2D view seen from the other side: every bearing the same, east and west swapped', () => {
    const above = { yaw: 0, tilt: 90 }
    for (const [alt, az] of [
      [10, 0],
      [30, 90],
      [50, 135],
      [70, 222],
      [20, 300],
    ]) {
      const flat = project(alt, az)
      const dome = project3d(alt, az, above)
      // the 2D view (from below) puts east on the left; from above it's on the right: x mirrors, y stays
      expect(Math.sign(dome.x)).toBe(-Math.sign(flat.x) || 0)
      expect(Math.sign(Math.round(dome.y))).toBe(Math.sign(Math.round(flat.y)))
      // the bearing from the zenith, measured to the matching compass letter, agrees in both
      const bearing = (p: { x: number; y: number }, mirror: number) =>
        ((((Math.atan2(mirror * p.x, -p.y) * 180) / Math.PI) % 360) + 360) % 360
      expect(bearing(dome, 1)).toBeCloseTo(az, 0)
      expect(bearing(flat, -1)).toBeCloseTo(az, 0)
    }
  })
  it('turns as a globe under the finger: dragging right carries the near side right', () => {
    const from = { yaw: 180, tilt: 32 }
    const to = dragView(from, 50, 0)
    const near = project3d(10, 0, from) // the north rim, nearest you
    expect(near.front).toBe(true)
    expect(project3d(10, 0, to).x).toBeGreaterThan(near.x)
    // and the other way
    expect(project3d(10, 0, dragView(from, -50, 0)).x).toBeLessThan(near.x)
    // dragging down looks from higher up, tipping the top towards you: the zenith comes down the drawing
    const lower = dragView(from, 0, 40)
    expect(lower.tilt).toBeGreaterThan(from.tilt)
    expect(project3d(90, 0, lower).y).toBeGreaterThan(project3d(90, 0, from).y)
    // yaw wraps; tilt stays between 8° and 85°
    expect(dragView({ yaw: 350, tilt: 32 }, 50, 0).yaw).toBeCloseTo(10)
    expect(dragView(from, 0, 1000).tilt).toBe(85)
    expect(dragView(from, 0, -1000).tilt).toBe(8)
  })
  it('splits a track where it crosses from the far wall to the near shell', () => {
    const view = { yaw: 180, tilt: 32 }
    const pts = [10, 30, 50, 70, 90, 70, 50].map((alt, i) => project3d(alt, i < 5 ? 180 : 0, view))
    const { front, back } = splitSides(pts)
    expect(back.length).toBe(1)
    expect(front.length).toBe(1)
    // the two pieces meet: the far piece ends where the near one starts
    expect(back[0][back[0].length - 1]).toEqual(front[0][0])
    expect(splitSides(pts.slice(0, 2))).toEqual({ front: [], back: [pts.slice(0, 2)] })
  })
})

describe('back from the drawing to the sky', () => {
  it('finds the sky on the far wall, and on the near shell when asked', () => {
    let checked = 0
    for (const [alt, az] of [
      [20, 180],
      [45, 150],
      [40, 220],
      [10, 120],
    ]) {
      const p = project3d(alt, az)
      expect(p.front).toBe(false)
      const back = unproject(p.x, p.y)!
      expect(back.alt).toBeCloseTo(alt, 1)
      expect(back.az).toBeCloseTo(az, 1)
      checked++
    }
    expect(checked).toBe(4)
    // under the near rim the line of sight meets the floor before any wall: no sky
    const rim = project3d(5, 0)
    expect(unproject(rim.x, rim.y - 2)).toBeNull()
  })
  it('undoes project3d on the near shell', () => {
    let checked = 0
    for (const [alt, az] of [
      [10, 200],
      [45, 30],
      [80, 120],
      [75, 300],
      [60, 0],
      [30, 180],
      [50, 150],
    ]) {
      const p = project3d(alt, az)
      const back = unproject(p.x, p.y, undefined, undefined, 'front')
      // the side facing the viewer comes back
      if (p.front && back) {
        checked++
        expect(back.alt).toBeCloseTo(alt, 1)
        expect(back.az).toBeCloseTo(az, 1)
      }
    }
    expect(checked).toBeGreaterThanOrEqual(2)
    expect(unproject(0, 200)).toBeNull() // off the dome
  })
  it('puts the zenith at the latitude and the sidereal time', () => {
    const lst = siderealDeg(Date.parse('2026-10-11T22:00:00Z'), -1.66)
    const z = toEquatorial(90, 0, 54.99, lst)
    expect(z.dec).toBeCloseTo(54.99, 5)
    expect(z.ra).toBeCloseTo(lst, 5)
  })
  it('knows the sidereal time (J2000.0 at Greenwich: 280.46°)', () => {
    expect(siderealDeg(Date.parse('2000-01-01T12:00:00Z'), 0)).toBeCloseTo(280.46, 1)
  })
  it('finds the Large Magellanic Cloud where the survey image has it', () => {
    const [x, y] = surveyPixel(80.9, -69.8, 2048, 1024)
    expect(x).toBeGreaterThan(1580)
    expect(x).toBeLessThan(1610)
    expect(y).toBeGreaterThan(900)
    expect(y).toBeLessThan(915)
  })
})

// the great-circle distance between two points, in degrees
const sep = (a: { ra: number; dec: number }, b: { ra: number; dec: number }) => {
  const r = Math.PI / 180
  const c =
    Math.sin(a.dec * r) * Math.sin(b.dec * r) +
    Math.cos(a.dec * r) * Math.cos(b.dec * r) * Math.cos((a.ra - b.ra) * r)
  return Math.acos(Math.min(1, c)) / r
}

describe('the camera frame on the dome (spec 015 amendment)', () => {
  it('turns equatorial into horizontal and back', () => {
    const lst = siderealDeg(Date.parse('2026-10-11T22:00:00Z'), -1.66)
    for (const [ra, dec] of [
      [314.75, 44.3],
      [83.8, -5.4],
      [10, 80],
    ]) {
      const h = toHorizontal(ra, dec, 54.99, lst)
      const e = toEquatorial(h.alt, h.az, 54.99, lst)
      expect(e.dec).toBeCloseTo(dec, 6)
      expect(((e.ra - ra + 540) % 360) - 180).toBeCloseTo(0, 6)
    }
    // the celestial pole stands due north at the latitude's altitude
    const pole = toHorizontal(0, 90, 54.99, lst)
    expect(pole.alt).toBeCloseTo(54.99, 6)
    expect(Math.min(pole.az, 360 - pole.az)).toBeCloseTo(0, 6)
  })
  it('steps east and north on the tangent plane', () => {
    expect(fromTangent(10, 0, 0, 0)).toEqual({ ra: 10, dec: 0 })
    const east = fromTangent(10, 0, 1, 0)
    expect(east.ra).toBeCloseTo(11, 2)
    expect(east.dec).toBeCloseTo(0, 6)
    const north = fromTangent(10, 40, 0, 2)
    expect(north.ra).toBeCloseTo(10, 6)
    expect(north.dec).toBeCloseTo(42, 2)
  })
  it('puts the corners where a north-up image has them: east on the left', () => {
    const fov = { ra_deg: 100, dec_deg: 0, w_deg: 4, h_deg: 2, rotation_deg: 0 }
    const pts = frameOutline(fov, 1)
    expect(pts).toHaveLength(4)
    const [tl, tr, br, bl] = pts
    expect(tl.ra).toBeCloseTo(102, 1) // top left: north and east
    expect(tl.dec).toBeCloseTo(1, 1)
    expect(tr.ra).toBeCloseTo(98, 1)
    expect(br.dec).toBeCloseTo(-1, 1)
    expect(bl.ra).toBeCloseTo(102, 1)
    // the sides keep their lengths wherever it points and however it's turned
    const turned = frameOutline({ ...fov, dec_deg: 60, rotation_deg: 37 }, 1)
    expect(sep(turned[0], turned[1])).toBeCloseTo(4, 1)
    expect(sep(turned[1], turned[2])).toBeCloseTo(2, 1)
    expect(sep(turned[0], turned[2])).toBeCloseTo(Math.hypot(4, 2), 1)
    // up turned to the east: the top edge now lies east of the centre
    const east = frameOutline({ ...fov, rotation_deg: 90 }, 1)
    expect((east[0].ra + east[1].ra) / 2).toBeCloseTo(101, 1)
  })
  it('draws the frame round the target on the dome, and not when it has set', () => {
    const t = Date.parse('2026-10-11T22:00:00Z')
    const fov = { ra_deg: 314.75, dec_deg: 44.3, w_deg: 3, h_deg: 2, rotation_deg: 0 }
    const f = frameOnDome(fov, 54.99, -1.66, t)!
    const h = toHorizontal(314.75, 44.3, 54.99, siderealDeg(t, -1.66))
    const c = project3d(h.alt, h.az)
    expect(f.centre.x).toBeCloseTo(c.x, 1)
    expect(f.centre.y).toBeCloseTo(c.y, 1)
    expect(f.d.endsWith('Z')).toBe(true)
    expect(f.d.match(/[ML]/g)).toHaveLength(24) // four sides of six steps
    expect(f.top.match(/[ML]/g)).toHaveLength(7)
    // every corner within a couple of degrees' worth of drawing of the centre
    for (const m of f.d.matchAll(/[ML](-?[\d.]+) (-?[\d.]+)/g))
      expect(Math.hypot(+m[1] - c.x, +m[2] - c.y)).toBeLessThan(4)
    // M 42 is below the horizon from Newcastle at 22:00 in October
    expect(frameOnDome({ ...fov, ra_deg: 83.8, dec_deg: -5.4 }, 54.99, -1.66, t)).toBeNull()
  })
})

describe('where a dome starts', () => {
  it('looks towards the target, and from higher up for a high one', () => {
    expect(homeFor([{ az: 10, alt: 30 }])).toEqual({ yaw: 0, tilt: 32 })
    expect(homeFor([{ az: 260, alt: 75 }])).toEqual({ yaw: 270, tilt: 62 })
    expect(homeFor([{ az: 180, alt: 45 }]).tilt).toBe(42)
  })
})
