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

// ---- the dome seen from outside (owner 2026-10-15; viewpoint settled 2026-10-22) ----------------------------
// The sky as a see-through wireframe dome standing on a horizon disc, seen from outside and above: the viewer stands
// on the far side from `yaw` (an azimuth; 180 looks south, where most targets cross the meridian), looks towards it,
// and looks down by `tilt` degrees. The half of the dome facing the viewer (`front`) is a faint shell to look
// through; the far half is seen from inside, so a target on it shows as it did from the ground facing `yaw`: looking
// south, east on the left. From straight above, north at the top, east is on the right (the 2D view, from below
// looking up, has it on the left: the same sky, mirrored by where you stand). Turning the view (yaw up) carries the
// near shell to the right, as a globe turns under a finger dragged right.

export type View = { yaw: number; tilt: number }
export const DEFAULT_VIEW: View = { yaw: 180, tilt: 32 }
export type Pt3 = Pt & { front: boolean }

const rad = (d: number) => (d * Math.PI) / 180

/** Where (altitude, azimuth) lands on the drawing; `front` is true on the near half, the shell between the viewer
 * and the far wall. */
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
    front: -ahead * Math.cos(tilt) + u * Math.sin(tilt) > 1e-9,
  }
}

/** The view after dragging `dx`, `dy` pixels from `from`: the near shell follows the pointer (right turns the
 * view's yaw up, carrying the near side right), and dragging down looks from higher up, tipping the top towards you. */
export function dragView(from: View, dx: number, dy: number): View {
  const yaw = from.yaw + dx * 0.4
  return {
    yaw: ((yaw % 360) + 360) % 360,
    tilt: Math.min(85, Math.max(8, from.tilt + dy * 0.3)),
  }
}

/** The drawing's extent for a view: the dome's top, the horizon's near edge, and room for the compass. */
export function domeBox(view: View = DEFAULT_VIEW, r = R) {
  const top = -r * Math.cos(rad(view.tilt)) - 10
  const bottom = r * Math.sin(rad(view.tilt)) + 14
  return { x: -r - 14, y: top, w: 2 * r + 28, h: bottom - top }
}

/** Points along the sky in pieces on the far wall (`back`) and the near shell (`front`), so each half can be drawn
 * in its own layer and weight; a piece crossing the dome's outline ends on it. */
export function splitSides(points: Pt3[]): { front: Pt[][]; back: Pt[][] } {
  const front: Pt[][] = []
  const back: Pt[][] = []
  let run: Pt[] = []
  let side: boolean | null = null
  for (const p of points) {
    if (side !== null && p.front !== side) {
      run.push(p)
      ;(side ? front : back).push(run)
      run = [p]
    } else run.push(p)
    side = p.front
  }
  if (run.length > 1 && side !== null) (side ? front : back).push(run)
  return { front, back }
}

/** A line along the sky (a ring or a meridian), as near and far paths so each half can be drawn in its own way. */
export function skyLine(points: [alt: number, az: number][], view: View = DEFAULT_VIEW, r = R) {
  const { front, back } = splitSides(points.map(([alt, az]) => project3d(alt, az, view, r)))
  return { front: front.map(polyline).join(' '), back: back.map(polyline).join(' ') }
}

/** An altitude ring all the way round. */
export const altRing = (alt: number) => Array.from({ length: 73 }, (_, i) => [alt, i * 5] as [number, number])
/** A meridian from the horizon to the zenith. */
export const azArc = (az: number) => Array.from({ length: 19 }, (_, i) => [i * 5, az] as [number, number])

// ---- from the drawing back to the sky (the survey behind the dome) ------------------------------------------

/** The sky at a point of the drawing: on the far wall (seen from inside, through the near shell) or, with `side`
 * 'front', on the near shell itself; null off the dome, and on the far wall where the line of sight reaches the floor
 * first. The inverse of project3d for points on that side. */
export function unproject(
  x: number,
  y: number,
  view: View = DEFAULT_VIEW,
  r = R,
  side: 'back' | 'front' = 'back',
): { alt: number; az: number } | null {
  const sx = x / r
  const up = -y / r
  const rest = 1 - sx * sx - up * up
  if (rest < 0) return null
  const tilt = rad(view.tilt)
  const yaw = rad(view.yaw)
  const t = (side === 'back' ? 1 : -1) * Math.sqrt(rest) // depth away from the viewer
  const ahead = up * Math.sin(tilt) + t * Math.cos(tilt)
  const u = up * Math.cos(tilt) - t * Math.sin(tilt)
  if (u < 0) return null
  const e = sx * Math.cos(yaw) + ahead * Math.sin(yaw)
  const n = -sx * Math.sin(yaw) + ahead * Math.cos(yaw)
  const az = (Math.atan2(e, n) * 180) / Math.PI
  return { alt: (Math.asin(Math.min(1, u)) * 180) / Math.PI, az: (az + 360) % 360 }
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

// ---- the camera's frame on the dome (spec 015 amendment, 2026-10-15) ----------------------------------------

/** Altitude and azimuth (degrees) of a right ascension and declination, for latitude `lat` and sidereal time `lst`
 * (degrees): the inverse of toEquatorial. Azimuth runs from north through east. */
export function toHorizontal(ra: number, dec: number, lat: number, lst: number): { alt: number; az: number } {
  const h = rad(lst - ra)
  const d = rad(dec)
  const p = rad(lat)
  const alt = Math.asin(Math.sin(p) * Math.sin(d) + Math.cos(p) * Math.cos(d) * Math.cos(h))
  const az = Math.atan2(
    -Math.cos(d) * Math.sin(h),
    Math.sin(d) * Math.cos(p) - Math.cos(d) * Math.cos(h) * Math.sin(p),
  )
  return { alt: (alt * 180) / Math.PI, az: ((((az * 180) / Math.PI) % 360) + 360) % 360 }
}

/** The sky at an offset from a centre, `east` and `north` in degrees on the tangent plane (the camera's flat image
 * of the sky: a gnomonic projection, as plate solving uses). */
export function fromTangent(
  ra0: number,
  dec0: number,
  east: number,
  north: number,
): { ra: number; dec: number } {
  const xi = rad(east)
  const eta = rad(north)
  const d0 = rad(dec0)
  const rho = Math.hypot(xi, eta)
  if (rho === 0) return { ra: ra0, dec: dec0 }
  const c = Math.atan(rho)
  const dec = Math.asin(Math.cos(c) * Math.sin(d0) + (eta * Math.sin(c) * Math.cos(d0)) / rho)
  const dra = Math.atan2(
    xi * Math.sin(c),
    rho * Math.cos(d0) * Math.cos(c) - eta * Math.sin(d0) * Math.sin(c),
  )
  const ra = ra0 + (dra * 180) / Math.PI
  return { ra: ((ra % 360) + 360) % 360, dec: (dec * 180) / Math.PI }
}

export type Fov = { ra_deg: number; dec_deg: number; w_deg: number; h_deg: number; rotation_deg: number }

/** The camera frame's outline on the sky, from its top-left corner round clockwise as the image is seen, each edge
 * divided into `steps` so it bends as it should on the dome. `rotation_deg` is the image's up direction, east of
 * north; the image's right is then a quarter turn west of up, as a sky image shown north up has east on the left. */
export function frameOutline(fov: Fov, steps = 6): { ra: number; dec: number }[] {
  const th = rad(fov.rotation_deg)
  const up = { e: Math.sin(th), n: Math.cos(th) }
  const right = { e: -Math.cos(th), n: Math.sin(th) }
  const w = fov.w_deg / 2
  const h = fov.h_deg / 2
  const corners: [number, number][] = [
    [-w, h],
    [w, h],
    [w, -h],
    [-w, -h],
  ]
  const out: { ra: number; dec: number }[] = []
  corners.forEach(([x0, y0], i) => {
    const [x1, y1] = corners[(i + 1) % 4]
    for (let k = 0; k < steps; k++) {
      const x = x0 + ((x1 - x0) * k) / steps
      const y = y0 + ((y1 - y0) * k) / steps
      out.push(fromTangent(fov.ra_deg, fov.dec_deg, x * right.e + y * up.e, x * right.n + y * up.n))
    }
  })
  return out
}

/** The camera's frame on the dome at time `t` (ms) from latitude/longitude: the closed outline, its top edge (the
 * image's up) on its own, and its centre; null when any of it is below the horizon. */
export function frameOnDome(
  fov: Fov,
  lat: number,
  lon: number,
  t: number,
  view: View = DEFAULT_VIEW,
  r = R,
): { d: string; top: string; centre: Pt3 } | null {
  const lst = siderealDeg(t, lon)
  const steps = 6
  const pts: Pt3[] = []
  for (const p of frameOutline(fov, steps)) {
    const h = toHorizontal(p.ra, p.dec, lat, lst)
    if (h.alt < 0) return null
    pts.push(project3d(h.alt, h.az, view, r))
  }
  const c = toHorizontal(fov.ra_deg, fov.dec_deg, lat, lst)
  return {
    d: polyline(pts) + 'Z',
    top: polyline([...pts.slice(0, steps), pts[steps]]),
    centre: project3d(c.alt, c.az, view, r),
  }
}

/** Which way to look to see a target on the far wall (2026-10-16): its usual azimuth, to the nearest eighth of a
 * turn. */
export function facingOf(subs: { az: number }[]): number {
  if (!subs.length) return DEFAULT_VIEW.yaw
  const x = subs.reduce((a, u) => a + Math.cos((u.az * Math.PI) / 180), 0)
  const y = subs.reduce((a, u) => a + Math.sin((u.az * Math.PI) / 180), 0)
  const az = ((((Math.atan2(y, x) * 180) / Math.PI) % 360) + 360) % 360
  return (Math.round(az / 45) * 45) % 360
}

/** Where to start looking from for a target (2026-10-16): looking towards it, so its track is on the far wall,
 * seen through the near shell, and from higher up the higher it was, so a track near the zenith sits inside the dome, not on its rim. */
export function homeFor(subs: { az: number; alt: number }[]): View {
  if (!subs.length) return DEFAULT_VIEW
  const alts = subs.map((x) => x.alt).sort((a, b) => a - b)
  const mid = alts[Math.floor(alts.length / 2)]
  // on the far wall a point at altitude h shows at height sin(h + tilt): up to 40° the usual 32° view; above that
  // two degrees higher for each degree, to 62°, so a high track sits inside the dome rather than on its rim
  const tilt = DEFAULT_VIEW.tilt + Math.max(0, mid - 40) * 2
  return { yaw: facingOf(subs), tilt: Math.round(Math.min(62, tilt)) }
}
