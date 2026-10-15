// The sky dome's geometry (spec 015): a zenithal equidistant view, as if lying on your back with north at the top.
// The zenith is the centre and the horizon the edge; altitude falls off evenly with distance, so the 30° and 60°
// rings are evenly spaced. Looking up, east is on the left and west on the right.

export const R = 100 // horizon radius in the drawing's units

export type Pt = { x: number; y: number }

/** Where (altitude, azimuth) in degrees lands on the dome; below the horizon lands outside the edge. */
export function project(alt: number, az: number, r = R): Pt {
  const rho = ((90 - alt) / 90) * r
  const a = (az * Math.PI) / 180
  return { x: round(-rho * Math.sin(a)), y: round(-rho * Math.cos(a)) }
}

const round = (n: number) => Math.round(n * 100) / 100

/** The radius of an altitude ring. */
export const ring = (alt: number, r = R) => ((90 - alt) / 90) * r

/** The compass points just outside the horizon. */
export function compass(r = R): { label: string; at: Pt }[] {
  return [
    { label: 'N', at: project(-9, 0, r) },
    { label: 'E', at: project(-9, 90, r) },
    { label: 'S', at: project(-9, 180, r) },
    { label: 'W', at: project(-9, 270, r) },
  ]
}

/** An SVG path through points, starting a new piece wherever `breaks` says. */
export function polyline(points: Pt[]): string {
  return points.map((p, i) => `${i ? 'L' : 'M'}${p.x} ${p.y}`).join(' ')
}

export type Shape = 'circle' | 'square' | 'triangle' | 'diamond' | 'cross'
export const SHAPES: Shape[] = ['circle', 'square', 'triangle', 'diamond', 'cross']

/** A marker's outline as a path centred on `p`, about `size` across, so every rig's dots read alike in weight. */
export function marker(shape: Shape, p: Pt, size: number): string {
  const h = size / 2
  const { x, y } = p
  switch (shape) {
    case 'square':
      return `M${x - h * 0.85} ${y - h * 0.85}h${h * 1.7}v${h * 1.7}h${-h * 1.7}Z`
    case 'triangle':
      return `M${x} ${y - h * 1.1}L${x + h} ${y + h * 0.75}L${x - h} ${y + h * 0.75}Z`
    case 'diamond':
      return `M${x} ${y - h * 1.15}L${x + h * 1.15} ${y}L${x} ${y + h * 1.15}L${x - h * 1.15} ${y}Z`
    case 'cross': {
      const t = h * 0.38
      return `M${x - t} ${y - h}h${2 * t}v${h - t}h${h - t}v${2 * t}h${t - h}v${h - t}h${-2 * t}v${t - h}h${t - h}v${-2 * t}h${h - t}Z`
    }
    default:
      return `M${x - h} ${y}a${h} ${h} 0 1 0 ${size} 0a${h} ${h} 0 1 0 ${-size} 0Z`
  }
}

/** The colour token for the n-th series. */
export const series = (n: number) => `var(--sst-series-${(n % 6) + 1})`

/** Linear interpolation of a value along timed samples (sorted by time); null outside them. */
export function at<T extends { time: string }>(
  samples: T[],
  t: number,
  value: (s: T) => number,
): number | null {
  if (!samples.length) return null
  const first = Date.parse(samples[0].time)
  const last = Date.parse(samples[samples.length - 1].time)
  if (t < first || t > last) return null
  for (let i = 1; i < samples.length; i++) {
    const b = Date.parse(samples[i].time)
    if (t <= b) {
      const a = Date.parse(samples[i - 1].time)
      const f = b === a ? 0 : (t - a) / (b - a)
      return value(samples[i - 1]) + (value(samples[i]) - value(samples[i - 1])) * f
    }
  }
  return value(samples[samples.length - 1])
}

/** Azimuth interpolated the short way round (350° → 10° passes through 0°, not 180°). */
export function azAt<T extends { time: string; az: number }>(samples: T[], t: number): number | null {
  const unwrapped: T[] = []
  let prev: number | null = null
  let turn = 0
  for (const s of samples) {
    if (prev != null && Math.abs(s.az - prev) > 180) turn += s.az < prev ? 360 : -360
    unwrapped.push({ ...s, az: s.az + turn })
    prev = s.az
  }
  const v = at(unwrapped, t, (s) => s.az)
  return v == null ? null : ((v % 360) + 360) % 360
}

/** Hour ticks across a span, on the hour. */
export function hourTicks(start: number, end: number): number[] {
  const out: number[] = []
  const h = 3_600_000
  for (let t = Math.ceil(start / h) * h; t <= end; t += h) out.push(t)
  return out
}

// ---- the dome seen from the side (owner 2026-10-15) ---------------------------------------------------------
// The sky as a wireframe dome over a horizon ellipse, seen from a little above and to one side: the viewer faces
// `yaw` (an azimuth; 180 faces south, where most targets cross the meridian) and looks down by `tilt` degrees.

export type View = { yaw: number; tilt: number }
export const DEFAULT_VIEW: View = { yaw: 180, tilt: 32 }
export type Pt3 = Pt & { front: boolean }

const rad = (d: number) => (d * Math.PI) / 180

/** Where (altitude, azimuth) lands on the drawing; `front` is true on the half of the dome facing the viewer. */
export function project3d(alt: number, az: number, view: View = DEFAULT_VIEW, r = R): Pt3 {
  const e = Math.sin(rad(az)) * Math.cos(rad(alt))
  const n = Math.cos(rad(az)) * Math.cos(rad(alt))
  const u = Math.sin(rad(alt))
  const yaw = rad(view.yaw)
  const tilt = rad(view.tilt)
  const right = e * Math.cos(yaw) - n * Math.sin(yaw) // the viewer's right
  const ahead = e * Math.sin(yaw) + n * Math.cos(yaw) // away from the viewer
  const up = u * Math.cos(tilt) + ahead * Math.sin(tilt)
  return {
    x: round(right * r),
    y: round(-up * r),
    front: -ahead * Math.cos(tilt) + u * Math.sin(tilt) >= -1e-9,
  }
}

/** The drawing's extent for a view: the dome's top, the horizon's near edge, and room for the compass. */
export function domeBox(view: View = DEFAULT_VIEW, r = R) {
  const top = -r * Math.cos(rad(view.tilt)) - 10
  const bottom = r * Math.sin(rad(view.tilt)) + 14
  return { x: -r - 14, y: top, w: 2 * r + 28, h: bottom - top }
}

/** A line along the sky (a ring or a meridian), as front and back pieces so the far side can be drawn fainter. */
export function skyLine(points: [alt: number, az: number][], view: View = DEFAULT_VIEW, r = R) {
  const front: Pt[][] = []
  const back: Pt[][] = []
  let run: Pt[] = []
  let side: boolean | null = null
  for (const [alt, az] of points) {
    const p = project3d(alt, az, view, r)
    if (side !== null && p.front !== side) {
      run.push(p)
      ;(side ? front : back).push(run)
      run = [p]
    } else run.push(p)
    side = p.front
  }
  if (run.length > 1 && side !== null) (side ? front : back).push(run)
  return { front: front.map(polyline).join(' '), back: back.map(polyline).join(' ') }
}

/** An altitude ring all the way round. */
export const altRing = (alt: number) => Array.from({ length: 73 }, (_, i) => [alt, i * 5] as [number, number])
/** A meridian from the horizon to the zenith. */
export const azArc = (az: number) => Array.from({ length: 19 }, (_, i) => [i * 5, az] as [number, number])

// ---- from the drawing back to the sky (the survey behind the dome) ------------------------------------------

/** The sky at a point of the drawing, on the side of the dome facing the viewer; null off the dome, and where that
 * side is below the horizon (looking down at the floor, which hides the far side). The inverse of project3d. */
export function unproject(
  x: number,
  y: number,
  view: View = DEFAULT_VIEW,
  r = R,
): { alt: number; az: number } | null {
  const sx = x / r
  const up = -y / r
  const rest = 1 - sx * sx - up * up
  if (rest < 0) return null
  const tilt = rad(view.tilt)
  const yaw = rad(view.yaw)
  // inside the horizon's ellipse is the floor: the near wall's lowest part lies over it, seen from outside
  if (sx * sx + (up / Math.sin(tilt)) ** 2 <= 1) return null
  for (const t of [-Math.sqrt(rest)]) {
    const ahead = up * Math.sin(tilt) + t * Math.cos(tilt)
    const u = up * Math.cos(tilt) - t * Math.sin(tilt)
    if (u < 0) return null
    const e = sx * Math.cos(yaw) + ahead * Math.sin(yaw)
    const n = -sx * Math.sin(yaw) + ahead * Math.cos(yaw)
    const az = (Math.atan2(e, n) * 180) / Math.PI
    return { alt: (Math.asin(Math.min(1, u)) * 180) / Math.PI, az: (az + 360) % 360 }
  }
  return null
}

/** Local sidereal time in degrees at `t` (ms since 1970) and east longitude `lon`. */
export function siderealDeg(t: number, lon: number): number {
  const jd = t / 86_400_000 + 2440587.5
  const gmst = 280.46061837 + 360.98564736629 * (jd - 2451545)
  return (((gmst + lon) % 360) + 360) % 360
}

/** Right ascension and declination (degrees) of an altitude and azimuth, for latitude `lat` and sidereal time. */
export function toEquatorial(alt: number, az: number, lat: number, lst: number): { ra: number; dec: number } {
  const a = rad(alt)
  const z = rad(az)
  const p = rad(lat)
  const dec = Math.asin(Math.sin(p) * Math.sin(a) + Math.cos(p) * Math.cos(a) * Math.cos(z))
  const ha = Math.atan2(
    -Math.sin(z) * Math.cos(a),
    Math.cos(p) * Math.sin(a) - Math.sin(p) * Math.cos(a) * Math.cos(z),
  )
  const ra = lst - (ha * 180) / Math.PI
  return { ra: ((ra % 360) + 360) % 360, dec: (dec * 180) / Math.PI }
}

/** Where (ra, dec) falls in the all-sky survey image: RA 360° at the left edge to 0° at the right, Dec +90° at top. */
export function surveyPixel(ra: number, dec: number, w: number, h: number): [number, number] {
  let x = w / 2 + ((180 - ra) / 360) * w
  x = ((x % w) + w) % w
  const y = Math.min(h - 1, Math.max(0, ((90 - dec) / 180) * h))
  return [Math.min(w - 1, Math.floor(x)), Math.floor(y)]
}
