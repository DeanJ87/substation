// The sky as it was shot (spec 015): a wireframe dome over the horizon, seen from the side, every sub a mark where
// its target stood at the middle of its exposure, joined into a track per target; a colour per target and a shape
// per rig. One target is in focus at a time (owner 2026-10-15); the others stay faint for context. Drag the dome,
// or use the arrow keys on it, to walk round it. A slider replays the night; under it, altitude against time. The tracks list and the table of subs say the
// same in words, for screen readers and keyboards.
import { useQuery } from '@tanstack/react-query'
import { type ReactNode, type RefObject, useEffect, useMemo, useRef, useState } from 'react'
import { api, unwrap } from '../../api/client'
import type { components } from '../../api/schema'
import { integrationText, timeText } from '../format'
import {
  type Pt,
  type Shape,
  type View,
  DEFAULT_VIEW,
  R,
  SHAPES,
  altRing,
  at,
  azArc,
  azAt,
  hourTicks,
  marker,
  polyline,
  project3d,
  series,
  skyLine,
} from './projection'
import { CREDIT, SkySurvey, type Survey } from './SkySurvey'
import s from './sky.module.css'

export type Sky = components['schemas']['SkyOut']
type SkySub = components['schemas']['SkySub']

type Focus = { kind: 'target' | 'rig'; key: string } | null

const SOURCE: Record<string, string> = {
  solve: 'plate solve',
  header: 'header RA/Dec',
  dataset: 'the dataset’s usual pointing',
}
const VERDICT: Record<string, string> = { accept: 'Accepted', down: 'Down-weighted', reject: 'Rejected' }

export function useNightSky(date: string, site: string | undefined) {
  return useQuery({
    queryKey: ['night-sky', date, site],
    enabled: !!site,
    queryFn: async () =>
      unwrap(await api.GET('/nights/{date}/sky', { params: { path: { date }, query: { site: site! } } })),
  })
}

/** Reduced motion asked for: Play steps instead of sweeping. */
function prefersReducedMotion(): boolean {
  return typeof window !== 'undefined' && !!window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
}

export function SkyView({ sky, onOpen }: { sky: Sky; onOpen: (sha: string) => void }) {
  const start = sky.start ? Date.parse(sky.start) : 0
  const end = sky.end ? Date.parse(sky.end) : 0
  const [now, setNow] = useState<number | null>(null) // null: the whole night
  const [playing, setPlaying] = useState(false)
  const [hidden, setHidden] = useState<Set<string>>(new Set())
  const [focus, setFocus] = useState<Focus>(null)
  const [hover, setHover] = useState<{ sub: SkySub; at: Pt } | null>(null)
  // the target in focus: the one with the most subs to start with
  const [chosen, setChosen] = useState<string | null>(null)
  const [view, setView] = useState<View>(DEFAULT_VIEW)
  const [survey, setSurvey] = useState<Survey>(() => {
    try {
      return (localStorage.getItem('sst-sky-survey') as Survey) || 'mellinger'
    } catch {
      return 'mellinger'
    }
  })
  const chooseSurvey = (x: Survey) => {
    setSurvey(x)
    try {
      localStorage.setItem('sst-sky-survey', x)
    } catch {
      /* private window: the choice lasts this visit */
    }
  }
  // orbit and zoom (owner 2026-10-15): drag turns and tilts; the wheel or a pinch zooms towards the pointer
  const drag = useRef<{ x: number; y: number; yaw: number; tilt: number } | null>(null)
  const pointers = useRef(new Map<number, { x: number; y: number }>())
  const pinch = useRef<number | null>(null)
  const [zoom, setZoom] = useState<{ k: number; cx: number; cy: number }>({
    k: 1,
    cx: FRAME_CX,
    cy: FRAME_CY,
  })
  const [moving, setMoving] = useState(false)
  const [svgEl, setSvgEl] = useState<SVGSVGElement | null>(null)

  const colourOf = useMemo(() => new Map(sky.targets.map((t, i) => [t.key, series(i)])), [sky.targets])
  const shapeOf = useMemo(
    () => new Map<string, Shape>(sky.rigs.map((r, i) => [r.key, SHAPES[i % SHAPES.length]])),
    [sky.rigs],
  )
  const many = sky.rigs.length > 1

  // Play: from the start (or where the slider is) to the end, then stop on the whole night
  const nowRef = useRef(now)
  useEffect(() => {
    nowRef.current = now
  }, [now])
  useEffect(() => {
    if (!playing) return
    const span = end - start
    if (prefersReducedMotion()) {
      const id = window.setInterval(() => {
        const next = (nowRef.current ?? start) + 30 * 60_000
        if (next >= end) {
          setNow(null)
          setPlaying(false)
        } else setNow(next)
      }, 700)
      return () => window.clearInterval(id)
    }
    let raf = 0
    let last = performance.now()
    const tick = (t: number) => {
      const next = (nowRef.current ?? start) + ((t - last) / 12_000) * span // the night in twelve seconds
      last = t
      if (next >= end) {
        setNow(null)
        setPlaying(false)
        return
      }
      setNow(next)
      raf = requestAnimationFrame(tick)
    }
    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
  }, [playing, start, end])

  const box = viewBoxFor(zoom)
  const zoomAt = (factor: number, point?: { x: number; y: number }) =>
    setZoom((z) => {
      const k = Math.min(6, Math.max(1, z.k * factor))
      if (k === 1) return { k: 1, cx: FRAME_CX, cy: FRAME_CY }
      const p = point ?? { x: z.cx, y: z.cy }
      const f = z.k / k
      return { k, cx: p.x + (z.cx - p.x) * f, cy: p.y + (z.cy - p.y) * f }
    })
  /** The drawing's coordinates under a point on the screen. */
  const toDrawing = (clientX: number, clientY: number) => {
    const r = svgEl?.getBoundingClientRect()
    if (!r || !r.width) return undefined
    return {
      x: box.x + ((clientX - r.left) / r.width) * box.w,
      y: box.y + ((clientY - r.top) / r.height) * box.h,
    }
  }
  /** Where the buttons zoom to: the middle of the focused target's marks, else the zenith. */
  const focusPoint = () => {
    const pts = sky.subs.filter((x) => sky.tracks[x.track]?.target === inFocus).map((x) => proj(x.alt, x.az))
    if (!pts.length) return proj(90, 0)
    return {
      x: pts.reduce((a, p) => a + p.x, 0) / pts.length,
      y: pts.reduce((a, p) => a + p.y, 0) / pts.length,
    }
  }
  const reset = () => {
    setView(DEFAULT_VIEW)
    setZoom({ k: 1, cx: FRAME_CX, cy: FRAME_CY })
  }
  // the wheel zooms (a native listener: React's wheel events can't stop the page scrolling)
  const zoomRef = useRef(zoomAt)
  const toDrawingRef = useRef(toDrawing)
  useEffect(() => {
    zoomRef.current = zoomAt
    toDrawingRef.current = toDrawing
  })
  useEffect(() => {
    const el = svgEl
    if (!el) return
    const wheel = (e: WheelEvent) => {
      e.preventDefault()
      zoomRef.current(Math.exp(-e.deltaY * 0.0015), toDrawingRef.current(e.clientX, e.clientY))
    }
    el.addEventListener('wheel', wheel, { passive: false })
    return () => el.removeEventListener('wheel', wheel)
  }, [svgEl])

  if (!sky.subs.length)
    return (
      <p className="muted">
        {sky.unplaced.length
          ? `None of this night’s ${sky.unplaced.length} subs can be placed on the sky: ${sky.unplaced[0].reason}`
          : 'No subs to place on the sky.'}
      </p>
    )

  const busiest = [...sky.targets].sort(
    (a, b) =>
      sky.tracks.filter((t) => t.target === b.key).reduce((n, t) => n + t.subs, 0) -
      sky.tracks.filter((t) => t.target === a.key).reduce((n, t) => n + t.subs, 0),
  )[0]?.key
  const inFocus = chosen ?? busiest
  const proj = (alt: number, az: number) => project3d(alt, az, view)

  const shown = (x: SkySub) => {
    const tr = sky.tracks[x.track]
    return !hidden.has(tr.target) && !hidden.has(tr.rig) && (now == null || Date.parse(x.time) <= now)
  }
  const dimmed = (track: number) => {
    const tr = sky.tracks[track]
    if (focus) return focus.kind === 'target' ? tr.target !== focus.key : tr.rig !== focus.key
    return tr.target !== inFocus
  }
  const toggle = (key: string) =>
    setHidden((h) => {
      const next = new Set(h)
      if (next.has(key)) next.delete(key)
      else next.add(key)
      return next
    })

  // one line per track segment, through the subs shown so far
  const lines: { key: string; track: number; d: string }[] = []
  const bySeg = new Map<string, Pt[]>()
  for (const x of sky.subs) {
    if (!shown(x)) continue
    const k = `${x.track}:${x.segment}`
    bySeg.set(k, [...(bySeg.get(k) ?? []), proj(x.alt, x.az)])
  }
  for (const [k, pts] of bySeg)
    if (pts.length > 1) lines.push({ key: k, track: +k.split(':')[0], d: polyline(pts) })

  const moonUp = (sky.moon?.points ?? []).filter((p) => p.alt > 0)
  const moonNow =
    now != null && sky.moon
      ? (() => {
          const alt = at(sky.moon.points, now, (p) => p.alt)
          const az = azAt(sky.moon.points, now)
          return alt != null && az != null && alt > 0 ? proj(alt, az) : null
        })()
      : null

  return (
    <div className={s.sky}>
      <div className={s.domeWrap}>
        {sky.lat != null && sky.lon != null && (
          <SkySurvey
            survey={survey}
            box={box}
            view={view}
            fast={moving}
            lat={sky.lat}
            lon={sky.lon}
            t={now ?? (start + end) / 2}
          />
        )}
        <svg
          className={s.dome}
          viewBox={`${box.x} ${box.y} ${box.w} ${box.h}`}
          role="img"
          aria-label={`The sky from where this night was shot, as a dome over the horizon facing ${facing(view.yaw)}: ${sky.subs.length} subs of ${sky.targets.length} target${sky.targets.length === 1 ? '' : 's'}. The tracks and the table below list the same.`}
          ref={setSvgEl}
          onPointerDown={(e) => {
            pointers.current.set(e.pointerId, { x: e.clientX, y: e.clientY })
            e.currentTarget.setPointerCapture?.(e.pointerId)
            drag.current = { x: e.clientX, y: e.clientY, yaw: view.yaw, tilt: view.tilt }
            pinch.current = null
            setMoving(true)
          }}
          onPointerMove={(e) => {
            if (!pointers.current.has(e.pointerId)) return
            pointers.current.set(e.pointerId, { x: e.clientX, y: e.clientY })
            const pts = [...pointers.current.values()]
            if (pts.length >= 2) {
              const d = Math.hypot(pts[0].x - pts[1].x, pts[0].y - pts[1].y)
              if (pinch.current)
                zoomAt(d / pinch.current, toDrawing((pts[0].x + pts[1].x) / 2, (pts[0].y + pts[1].y) / 2))
              pinch.current = d
              return
            }
            if (!drag.current) return
            const yaw = drag.current.yaw - (e.clientX - drag.current.x) * 0.4
            const tilt = Math.min(85, Math.max(8, drag.current.tilt + (e.clientY - drag.current.y) * 0.3))
            setView({ yaw: ((yaw % 360) + 360) % 360, tilt })
          }}
          onPointerUp={(e) => {
            pointers.current.delete(e.pointerId)
            if (!pointers.current.size) {
              drag.current = null
              pinch.current = null
              setMoving(false)
            }
          }}
          onPointerCancel={(e) => {
            pointers.current.delete(e.pointerId)
            drag.current = null
            pinch.current = null
            setMoving(false)
          }}
        >
          <path d={polyline(altRing(0).map(([a, z]) => proj(a, z))) + 'Z'} className={s.ground} />
          {[30, 60].map((a) => (
            <path key={`b${a}`} d={skyLine(altRing(a), view).back} className={s.gridBack} />
          ))}
          {[0, 45, 90, 135, 180, 225, 270, 315].map((az) => (
            <path key={`mb${az}`} d={skyLine(azArc(az), view).back} className={s.gridBack} />
          ))}
          <path d={skyLine(altRing(0), view).back} className={s.horizonBack} />
          {/* the dome's outline, seen side on: half a circle from the horizon's east end to its west end */}
          <path d={`M${-R} 0A${R} ${R} 0 0 1 ${R} 0`} className={s.limb} />
          <path d={skyLine(altRing(0), view).front} className={s.horizon} />
          {[30, 60].map((a) => (
            <path key={`f${a}`} d={skyLine(altRing(a), view).front} className={s.alt} />
          ))}
          {[0, 45, 90, 135, 180, 225, 270, 315].map((az) => (
            <path
              key={`mf${az}`}
              d={skyLine(azArc(az), view).front}
              className={az % 180 === 0 ? s.meridian : s.alt}
            />
          ))}
          {[30, 60].map((a) => {
            const p = proj(a, view.yaw + 200) // on the near side, just off the near meridian
            return (
              <text key={a} x={p.x + 2} y={p.y - 2} className={s.ringLabel}>
                {a}°
              </text>
            )
          })}
          {(
            [
              ['N', 0],
              ['E', 90],
              ['S', 180],
              ['W', 270],
            ] as const
          ).map(([label, az]) => {
            const p = proj(-7, az)
            return (
              <text
                key={label}
                x={p.x}
                y={p.y + 3}
                className={`${s.compass} ${p.front ? '' : s.compassBack}`}
                textAnchor="middle"
              >
                {label}
              </text>
            )
          })}
          {moonUp.length > 1 && (
            <path d={polyline(moonUp.map((p) => proj(p.alt, p.az)))} className={s.moonTrack} />
          )}
          {lines.map((l) => (
            <path
              key={l.key}
              d={l.d}
              className={`${s.track} ${dimmed(l.track) ? s.dim : ''}`}
              style={{ stroke: colourOf.get(sky.tracks[l.track].target) }}
            />
          ))}
          {sky.subs.filter(shown).map((x) => {
            const p = proj(x.alt, x.az)
            const tr = sky.tracks[x.track]
            const colour = colourOf.get(tr.target)
            const reject = x.verdict === 'reject'
            return (
              <path
                key={x.sha256}
                d={marker(shapeOf.get(tr.rig) ?? 'circle', p, 4.2 / zoom.k)}
                className={`${s.mark} ${x.verdict === 'down' ? s.faded : ''} ${dimmed(x.track) ? s.dim : ''}`}
                style={
                  reject ? { stroke: colour, fill: 'var(--sst-panel)' } : { fill: colour, stroke: colour }
                }
                onMouseEnter={() => setHover({ sub: x, at: p })}
                onMouseLeave={() => setHover(null)}
                onClick={() => onOpen(x.sha256)}
              />
            )
          })}
          {now != null &&
            sky.targets
              .filter((t) => !hidden.has(t.key) && t.key === (focus?.kind === 'target' ? focus.key : inFocus))
              .map((t) => {
                const alt = at(t.curve, now, (p) => p.alt)
                const az = azAt(t.curve, now)
                if (alt == null || az == null || alt < 0) return null
                const p = proj(alt, az)
                return (
                  <circle
                    key={t.key}
                    cx={p.x}
                    cy={p.y}
                    r={5 / zoom.k}
                    className={s.now}
                    style={{ stroke: colourOf.get(t.key) }}
                  />
                )
              })}
          {moonNow && <circle cx={moonNow.x} cy={moonNow.y} r={4.5 / zoom.k} className={s.moon} />}
        </svg>
        {hover && <Tip sub={hover.sub} at={hover.at} sky={sky} box={box} />}
        <p className={s.turnHint}>
          <span>
            Facing {facing(view.yaw)} · {Math.round(view.tilt)}° up · drag to turn, scroll to zoom
          </span>
          <span className={s.surveyPick} role="group" aria-label="View">
            <button
              type="button"
              className={s.turn}
              onClick={() => setView((v) => ({ ...v, yaw: (v.yaw + 315) % 360 }))}
              aria-label="Turn left"
            >
              ←
            </button>
            <button
              type="button"
              className={s.turn}
              onClick={() => setView((v) => ({ ...v, yaw: (v.yaw + 45) % 360 }))}
              aria-label="Turn right"
            >
              →
            </button>
            <button
              type="button"
              className={s.turn}
              onClick={() => zoomAt(1 / 1.4, focusPoint())}
              aria-label="Zoom out"
              disabled={zoom.k <= 1}
            >
              −
            </button>
            <button
              type="button"
              className={s.turn}
              onClick={() => zoomAt(1.4, focusPoint())}
              aria-label="Zoom in"
              disabled={zoom.k >= 6}
            >
              +
            </button>
          </span>
          <span className={s.surveyPick} role="group" aria-label="Sky behind the dome">
            {(
              [
                ['mellinger', 'Mellinger'],
                ['dss', 'DSS'],
                ['off', 'No sky'],
              ] as const
            ).map(([k, label]) => (
              <button
                key={k}
                type="button"
                className={s.turn}
                aria-pressed={survey === k}
                onClick={() => chooseSurvey(k)}
              >
                {label}
              </button>
            ))}
          </span>
          {(view.yaw !== DEFAULT_VIEW.yaw || view.tilt !== DEFAULT_VIEW.tilt || zoom.k !== 1) && (
            <button type="button" className={s.linkButton} onClick={reset}>
              Reset view
            </button>
          )}
        </p>
        {survey !== 'off' && <p className={s.credit}>{CREDIT[survey]}</p>}
      </div>

      <div className={s.side}>
        <Key
          sky={sky}
          colourOf={colourOf}
          shapeOf={shapeOf}
          many={many}
          hidden={hidden}
          toggle={toggle}
          setFocus={setFocus}
          inFocus={inFocus}
          choose={setChosen}
        />
        <Facts sky={sky} />
      </div>

      <div className={s.play}>
        <button
          type="button"
          className={s.playButton}
          aria-pressed={playing}
          onClick={() => {
            if (!playing && now == null) setNow(start)
            setPlaying(!playing)
          }}
        >
          {playing ? 'Pause' : 'Play the night'}
        </button>
        <input
          type="range"
          className={s.slider}
          min={start}
          max={end}
          step={60_000}
          value={now ?? end}
          aria-label="Time through the night"
          aria-valuetext={now == null ? 'The whole night' : timeText(new Date(now).toISOString())}
          onChange={(e) => {
            setPlaying(false)
            const v = Number(e.target.value)
            setNow(v >= end ? null : v)
          }}
        />
        <span className={s.clock}>{now == null ? 'Whole night' : timeText(new Date(now).toISOString())}</span>
      </div>

      <AltitudeChart sky={sky} colourOf={colourOf} hidden={hidden} now={now} />
    </div>
  )
}

const exposure = (x: number | null | undefined) => (x != null ? `${x % 1 ? x.toFixed(1) : x} s` : '')
const fwhm = (x: SkySub) =>
  x.fwhm_arcsec != null
    ? `FWHM ${x.fwhm_arcsec.toFixed(2)}″`
    : x.fwhm_px != null
      ? `FWHM ${x.fwhm_px.toFixed(2)} px`
      : ''

// one fixed frame for every tilt, so the drawing doesn't change height as it turns
const FRAME = { x: -114, y: -110, w: 228, h: 182 }
const FRAME_CX = FRAME.x + FRAME.w / 2
const FRAME_CY = FRAME.y + FRAME.h / 2
function viewBoxFor(z: { k: number; cx: number; cy: number }) {
  const w = FRAME.w / z.k
  const h = FRAME.h / z.k
  return { x: z.cx - w / 2, y: z.cy - h / 2, w, h }
}

const COMPASS = ['north', 'north-east', 'east', 'south-east', 'south', 'south-west', 'west', 'north-west']
const facing = (yaw: number) => COMPASS[Math.round(yaw / 45) % 8]

function Tip({
  sub,
  at: p,
  sky,
  box,
}: {
  sub: SkySub
  at: Pt
  sky: Sky
  box: { x: number; y: number; w: number; h: number }
}) {
  const tr = sky.tracks[sub.track]
  const rig = sky.rigs.find((r) => r.key === tr.rig)?.name
  const left = ((p.x - box.x) / box.w) * 100
  const top = ((p.y - box.y) / box.h) * 100
  return (
    <div className={s.tip} style={{ left: `${left}%`, top: `${top}%` }} role="status">
      <strong>{tr.label}</strong>
      <span>{[timeText(sub.time), exposure(sub.exptime_s), rig].filter(Boolean).join(' · ')}</span>
      <span>
        Altitude {Math.round(sub.alt)}°, azimuth {Math.round(sub.az)}°
      </span>
      <span>{[VERDICT[sub.verdict ?? ''] ?? 'Not graded', fwhm(sub)].filter(Boolean).join(' · ')}</span>
    </div>
  )
}

function Swatch({ colour, shape }: { colour?: string; shape: Shape }) {
  return (
    <svg className={s.swatch} viewBox="-6 -6 12 12" aria-hidden="true">
      <path d={marker(shape, { x: 0, y: 0 }, 8)} style={{ fill: colour ?? 'var(--sst-muted)' }} />
    </svg>
  )
}

function Key({
  sky,
  colourOf,
  shapeOf,
  many,
  hidden,
  toggle,
  setFocus,
  inFocus,
  choose,
}: {
  sky: Sky
  colourOf: Map<string, string>
  shapeOf: Map<string, Shape>
  many: boolean
  hidden: Set<string>
  toggle: (key: string) => void
  setFocus: (f: Focus) => void
  inFocus: string | undefined
  choose: (key: string) => void
}) {
  // a target row brings that target into focus; a rig row shows or hides that rig
  const row = (kind: 'target' | 'rig', key: string, name: string, swatch: ReactNode, detail: string) => (
    <li key={key}>
      <button
        type="button"
        className={`${s.keyRow} ${kind === 'target' ? s.keyTarget : ''} ${kind === 'target' && key === inFocus ? s.keyOn : ''}`}
        aria-pressed={kind === 'target' ? key === inFocus : !hidden.has(key)}
        onClick={() => (kind === 'target' ? choose(key) : toggle(key))}
        onMouseEnter={() => setFocus({ kind, key })}
        onMouseLeave={() => setFocus(null)}
        onFocus={() => setFocus({ kind, key })}
        onBlur={() => setFocus(null)}
      >
        {swatch}
        <span className={s.keyName}>{name}</span>
        <span className={s.keyDetail}>{detail}</span>
      </button>
    </li>
  )
  const subsOf = (pred: (t: Sky['tracks'][number]) => boolean) =>
    sky.tracks.filter(pred).reduce((a, t) => a + t.subs, 0)
  return (
    <div className={s.key}>
      <h3 className="label">Targets</h3>
      <ul className={s.keyList}>
        {sky.targets.map((t) =>
          row(
            'target',
            t.key,
            t.name,
            <Swatch colour={colourOf.get(t.key)} shape="circle" />,
            `${subsOf((x) => x.target === t.key)} subs`,
          ),
        )}
      </ul>
      {many && (
        <>
          <h3 className="label">Rigs</h3>
          <ul className={s.keyList}>
            {sky.rigs.map((r) =>
              row(
                'rig',
                r.key,
                r.name,
                <Swatch shape={shapeOf.get(r.key) ?? 'circle'} />,
                `${subsOf((x) => x.rig === r.key)} subs`,
              ),
            )}
          </ul>
        </>
      )}
      <p className={s.keyHint}>
        Filled: kept. Faded: down-weighted. Hollow: rejected. Choose a target to bring it into focus
        {many ? '; a rig to hide or show it' : ''}.
      </p>
    </div>
  )
}

function Facts({ sky }: { sky: Sky }) {
  const tw = sky.twilight
  const moon = sky.moon
  const highest = moon?.points.reduce((a, p) => (p.alt > a ? p.alt : a), -90) ?? -90
  return (
    <dl className={s.facts}>
      {tw?.dusk && tw.dawn && (
        <>
          <dt>Astronomical dark</dt>
          <dd>
            {hm(tw.dusk)} to {hm(tw.dawn)}
          </dd>
        </>
      )}
      {moon && (
        <>
          <dt>Moon</dt>
          <dd>
            {Math.round(moon.illumination * 100)}% lit
            {highest > 0 ? `, up to ${Math.round(highest)}°` : ', below the horizon'}
          </dd>
        </>
      )}
      {sky.unplaced.length > 0 && (
        <>
          <dt>Not on the sky</dt>
          <dd>
            {sky.unplaced.length} sub{sky.unplaced.length === 1 ? '' : 's'}: {sky.unplaced[0].reason}
          </dd>
        </>
      )}
    </dl>
  )
}

const H = 190
const PAD = { l: 36, r: 8, t: 8, b: 22 }

/** The element's width in pixels, so the chart's text stays the same size at any width. */
function useWidth<T extends HTMLElement>(fallback: number): [RefObject<T | null>, number] {
  const ref = useRef<T>(null)
  const [w, setW] = useState(fallback)
  useEffect(() => {
    const el = ref.current
    if (!el || typeof ResizeObserver === 'undefined') return
    const ro = new ResizeObserver(([e]) => setW(Math.max(Math.round(e.contentRect.width), 280)))
    ro.observe(el)
    return () => ro.disconnect()
  }, [])
  return [ref, w]
}

const hm = (iso: string) => new Date(iso).toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' })

function AltitudeChart({
  sky,
  colourOf,
  hidden,
  now,
}: {
  sky: Sky
  colourOf: Map<string, string>
  hidden: Set<string>
  now: number | null
}) {
  const [box, W] = useWidth<HTMLElement>(600)
  const start = Date.parse(sky.start!)
  const end = Date.parse(sky.end!)
  const x = (t: number) => PAD.l + ((t - start) / (end - start)) * (W - PAD.l - PAD.r)
  const y = (alt: number) => PAD.t + (1 - Math.max(alt, 0) / 90) * (H - PAD.t - PAD.b)
  const path = (pts: { time: string; alt: number }[]) =>
    pts
      .filter((p) => p.alt >= 0)
      .map((p, i) => `${i ? 'L' : 'M'}${x(Date.parse(p.time)).toFixed(1)} ${y(p.alt).toFixed(1)}`)
      .join(' ')
  const tw = sky.twilight
  const dusk = tw?.dusk ? Math.max(Date.parse(tw.dusk), start) : null
  const dawn = tw?.dawn ? Math.min(Date.parse(tw.dawn), end) : null
  return (
    <figure className={s.chart} ref={box}>
      <figcaption className="label">Altitude through the night</figcaption>
      <svg
        viewBox={`0 0 ${W} ${H}`}
        role="img"
        aria-label="Each target’s altitude against time, with the Moon and twilight"
      >
        {dusk != null && dusk > start && (
          <rect
            x={x(start)}
            y={PAD.t}
            width={x(dusk) - x(start)}
            height={H - PAD.t - PAD.b}
            className={s.twilight}
          />
        )}
        {dawn != null && dawn < end && (
          <rect
            x={x(dawn)}
            y={PAD.t}
            width={x(end) - x(dawn)}
            height={H - PAD.t - PAD.b}
            className={s.twilight}
          />
        )}
        {[0, 30, 60, 90].map((a) => (
          <g key={a}>
            <line x1={PAD.l} x2={W - PAD.r} y1={y(a)} y2={y(a)} className={a === 30 ? s.thirty : s.grid} />
            <text x={PAD.l - 6} y={y(a) + 4} textAnchor="end" className={s.axisText}>
              {a}°
            </text>
          </g>
        ))}
        {hourTicks(start, end)
          .filter((_, i, all) => all.length * 56 < W || i % 2 === 0)
          .map((t) => (
            <text key={t} x={x(t)} y={H - 6} textAnchor="middle" className={s.axisText}>
              {new Date(t).toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' })}
            </text>
          ))}
        {sky.moon && <path d={path(sky.moon.points)} className={s.moonLine} />}
        {sky.targets
          .filter((t) => !hidden.has(t.key))
          .map((t) => (
            <path key={t.key} d={path(t.curve)} className={s.curve} style={{ stroke: colourOf.get(t.key) }} />
          ))}
        {sky.subs
          .filter((u) => !hidden.has(sky.tracks[u.track].target) && !hidden.has(sky.tracks[u.track].rig))
          .map((u) => (
            <circle
              key={u.sha256}
              cx={x(Date.parse(u.time))}
              cy={y(u.alt)}
              r={2.2}
              className={u.verdict === 'reject' ? s.chartReject : s.chartMark}
              style={{
                fill: u.verdict === 'reject' ? 'var(--sst-panel)' : colourOf.get(sky.tracks[u.track].target),
                stroke: colourOf.get(sky.tracks[u.track].target),
              }}
            />
          ))}
        {now != null && <line x1={x(now)} x2={x(now)} y1={PAD.t} y2={H - PAD.b} className={s.nowLine} />}
      </svg>
    </figure>
  )
}

/** The tracks in words: target, filter, rig, when and how much (FR-008). */
export function SkyTracks({ sky }: { sky: Sky }) {
  const colourOf = new Map(sky.targets.map((t, i) => [t.key, series(i)]))
  const shapeOf = new Map<string, Shape>(sky.rigs.map((r, i) => [r.key, SHAPES[i % SHAPES.length]]))
  if (!sky.tracks.length) return null
  return (
    <ul className={s.tracks} aria-label="Tracks">
      {sky.tracks.map((t) => (
        <li key={t.dataset_id}>
          <Swatch colour={colourOf.get(t.target)} shape={shapeOf.get(t.rig) ?? 'circle'} />
          <span className={s.trackName}>{t.label}</span>
          <span className="muted">
            {sky.rigs.find((r) => r.key === t.rig)?.name} · {hm(t.first)} to {hm(t.last)} ·{' '}
            {integrationText(t.integration_s)} · {t.subs} subs
          </span>
        </li>
      ))}
    </ul>
  )
}

/** Every placed sub as a row, for keyboards and screen readers: each opens the viewer. */
export function SkyTable({ sky, onOpen }: { sky: Sky; onOpen: (sha: string) => void }) {
  if (!sky.subs.length) return null
  return (
    <details className={s.table}>
      <summary>Every sub on the sky, as a table</summary>
      <div className={s.tableScroll}>
        <table className="cards">
          <thead>
            <tr>
              <th scope="col">Time</th>
              <th scope="col">Track</th>
              <th scope="col">Altitude</th>
              <th scope="col">Azimuth</th>
              <th scope="col">Grade</th>
              <th scope="col">Pointing from</th>
            </tr>
          </thead>
          <tbody>
            {sky.subs.map((x) => (
              <tr key={x.sha256}>
                <td>
                  <button type="button" className={s.linkish} onClick={() => onOpen(x.sha256)}>
                    {timeText(x.time)}
                  </button>
                </td>
                <td data-label="Track" data-wide>
                  {sky.tracks[x.track].label}
                </td>
                <td data-label="Altitude">{Math.round(x.alt)}°</td>
                <td data-label="Azimuth">{Math.round(x.az)}°</td>
                <td data-label="Grade">{VERDICT[x.verdict ?? ''] ?? 'Not graded'}</td>
                <td data-label="Pointing from">{SOURCE[x.source] ?? x.source}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </details>
  )
}
