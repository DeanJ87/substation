// The dome itself (spec 015): a wireframe hemisphere over the horizon seen from the side, the real sky behind it,
// orbited by dragging (sideways turns, up and down tilts), zoomed by the wheel or a pinch, with buttons for keyboards.
// The night view and the across-nights view draw their tracks into it (015-DR-05, -07, -08, N7).
import { type PointerEvent, type ReactNode, useEffect, useRef, useState } from 'react'
import {
  type Pt,
  type Pt3,
  type View,
  DEFAULT_VIEW,
  R,
  altRing,
  azArc,
  polyline,
  project3d,
  skyLine,
} from './projection'
import { CREDIT, SkySurvey, type Survey } from './SkySurvey'
import s from './sky.module.css'

export type Box = { x: number; y: number; w: number; h: number }
export type DomeCtx = { proj: (alt: number, az: number) => Pt3; view: View; k: number; box: Box }

// one fixed frame for every tilt, so the drawing doesn't change height as it turns
// tall enough for the horizon's near edge at the steepest starting view (62°: R·sin 62° ≈ 88, plus its compass letters)
const FRAME = { x: -114, y: -110, w: 228, h: 216 }
const FRAME_CX = FRAME.x + FRAME.w / 2
const FRAME_CY = FRAME.y + FRAME.h / 2
function viewBoxFor(z: { k: number; cx: number; cy: number }): Box {
  const w = FRAME.w / z.k
  const h = FRAME.h / z.k
  return { x: z.cx - w / 2, y: z.cy - h / 2, w, h }
}

const COMPASS = ['north', 'north-east', 'east', 'south-east', 'south', 'south-west', 'west', 'north-west']
export const facing = (yaw: number) => COMPASS[Math.round(yaw / 45) % 8]

function useSurveyChoice(): [Survey, (x: Survey) => void] {
  const [survey, setSurvey] = useState<Survey>(() => {
    try {
      return (localStorage.getItem('sst-sky-survey') as Survey) || 'mellinger'
    } catch {
      return 'mellinger'
    }
  })
  const choose = (x: Survey) => {
    setSurvey(x)
    try {
      localStorage.setItem('sst-sky-survey', x)
    } catch {
      /* private window: the choice lasts this visit */
    }
  }
  return [survey, choose]
}

/** Drag to orbit, two fingers to pinch, the wheel to zoom towards the pointer. */
function useOrbit(svgEl: SVGSVGElement | null, home: View) {
  const [view, setView] = useState<View>(home)
  const [zoom, setZoom] = useState({ k: 1, cx: FRAME_CX, cy: FRAME_CY })
  const [moving, setMoving] = useState(false)
  const drag = useRef<{ x: number; y: number; yaw: number; tilt: number } | null>(null)
  const pointers = useRef(new Map<number, { x: number; y: number }>())
  const pinch = useRef<number | null>(null)
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
  // the wheel zooms (a native listener: React's wheel events can't stop the page scrolling)
  const latest = useRef({ zoomAt, toDrawing })
  useEffect(() => {
    latest.current = { zoomAt, toDrawing }
  })
  useEffect(() => {
    const el = svgEl
    if (!el) return
    const wheel = (e: WheelEvent) => {
      e.preventDefault()
      latest.current.zoomAt(Math.exp(-e.deltaY * 0.0015), latest.current.toDrawing(e.clientX, e.clientY))
    }
    el.addEventListener('wheel', wheel, { passive: false })
    return () => el.removeEventListener('wheel', wheel)
  }, [svgEl])

  const stop = () => {
    drag.current = null
    pinch.current = null
    setMoving(false)
  }
  const handlers = {
    onPointerDown: (e: PointerEvent<SVGSVGElement>) => {
      pointers.current.set(e.pointerId, { x: e.clientX, y: e.clientY })
      e.currentTarget.setPointerCapture?.(e.pointerId)
      drag.current = { x: e.clientX, y: e.clientY, yaw: view.yaw, tilt: view.tilt }
      pinch.current = null
      setMoving(true)
    },
    onPointerMove: (e: PointerEvent<SVGSVGElement>) => {
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
    },
    onPointerUp: (e: PointerEvent<SVGSVGElement>) => {
      pointers.current.delete(e.pointerId)
      if (!pointers.current.size) stop()
    },
    onPointerCancel: (e: PointerEvent<SVGSVGElement>) => {
      pointers.current.delete(e.pointerId)
      stop()
    },
  }
  const reset = () => {
    setView(home)
    setZoom({ k: 1, cx: FRAME_CX, cy: FRAME_CY })
  }
  return { view, setView, zoom, box, moving, zoomAt, handlers, reset }
}

function Grid({ view, proj }: { view: View; proj: (alt: number, az: number) => Pt3 }) {
  const meridians = [0, 45, 90, 135, 180, 225, 270, 315]
  return (
    <>
      <path d={polyline(altRing(0).map(([a, z]) => proj(a, z))) + 'Z'} className={s.ground} />
      {[30, 60].map((a) => (
        <path key={`b${a}`} d={skyLine(altRing(a), view).back} className={s.gridBack} />
      ))}
      {meridians.map((az) => (
        <path key={`mb${az}`} d={skyLine(azArc(az), view).back} className={s.gridBack} />
      ))}
      <path d={skyLine(altRing(0), view).back} className={s.horizonBack} />
      {/* the dome's outline, seen side on: half a circle from the horizon's east end to its west end */}
      <path d={`M${-R} 0A${R} ${R} 0 0 1 ${R} 0`} className={s.limb} />
      <path d={skyLine(altRing(0), view).front} className={s.horizon} />
      {[30, 60].map((a) => (
        <path key={`f${a}`} d={skyLine(altRing(a), view).front} className={s.alt} />
      ))}
      {meridians.map((az) => (
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
    </>
  )
}

export function Dome({
  lat,
  lon,
  t,
  label,
  zoomTarget,
  children,
  renderOverlay,
  home = DEFAULT_VIEW,
  spin = false,
}: {
  lat: number | null
  lon: number | null
  t: number // the moment the sky behind is shown for
  label: (facing: string) => string
  zoomTarget: (proj: DomeCtx['proj']) => Pt | null // where the zoom buttons zoom towards
  children: (ctx: DomeCtx) => ReactNode
  renderOverlay?: (ctx: DomeCtx) => ReactNode
  home?: View // where the view starts, and Reset view returns
  spin?: boolean // while playing, the view slowly walks round the dome, as a filmed sky would (not with reduced motion)
}) {
  const [svgEl, setSvgEl] = useState<SVGSVGElement | null>(null)
  const [survey, chooseSurvey] = useSurveyChoice()
  const { view, setView, zoom, box, moving, zoomAt, handlers, reset } = useOrbit(svgEl, home)
  // the slow walk round while playing; a drag (moving) takes over from it
  useEffect(() => {
    if (!spin || moving) return
    if (typeof window !== 'undefined' && window.matchMedia?.('(prefers-reduced-motion: reduce)').matches)
      return
    let raf = 0
    let last = performance.now()
    const tick = (now: number) => {
      const d = (now - last) * 0.006 // six degrees a second
      last = now
      setView((v) => ({ ...v, yaw: (v.yaw + d) % 360 }))
      raf = requestAnimationFrame(tick)
    }
    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
  }, [spin, moving, setView])
  const proj = (alt: number, az: number) => project3d(alt, az, view)
  const ctx: DomeCtx = { proj, view, k: zoom.k, box }
  const towards = () => zoomTarget(proj) ?? proj(90, 0)
  return (
    <div className={s.domeWrap}>
      {lat != null && lon != null && (
        <SkySurvey survey={survey} box={box} view={view} fast={moving || spin} lat={lat} lon={lon} t={t} />
      )}
      <svg
        className={s.dome}
        viewBox={`${box.x} ${box.y} ${box.w} ${box.h}`}
        role="img"
        aria-label={label(facing(view.yaw))}
        ref={setSvgEl}
        {...handlers}
      >
        <defs>
          {/* which way a track went: an arrowhead at its latest end, in the track's own colour */}
          <marker
            id="sky-arrow"
            viewBox="0 0 10 10"
            refX="6"
            refY="5"
            markerWidth="5"
            markerHeight="5"
            orient="auto"
            markerUnits="strokeWidth"
          >
            <path d="M0 0L10 5L0 10z" fill="context-stroke" />
          </marker>
        </defs>
        <Grid view={view} proj={proj} />
        {children(ctx)}
      </svg>
      {renderOverlay?.(ctx)}
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
            onClick={() => zoomAt(1 / 1.4, towards())}
            aria-label="Zoom out"
            disabled={zoom.k <= 1}
          >
            −
          </button>
          <button
            type="button"
            className={s.turn}
            onClick={() => zoomAt(1.4, towards())}
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
          ).map(([k, name]) => (
            <button
              key={k}
              type="button"
              className={s.turn}
              aria-pressed={survey === k}
              onClick={() => chooseSurvey(k)}
            >
              {name}
            </button>
          ))}
        </span>
        {(view.yaw !== home.yaw || view.tilt !== home.tilt || zoom.k !== 1) && (
          <button type="button" className={s.linkButton} onClick={reset}>
            Reset view
          </button>
        )}
      </p>
      {survey !== 'off' && <p className={s.credit}>{CREDIT[survey]}</p>}
    </div>
  )
}

/** The middle of some points on the drawing, for the zoom buttons. */
export function middle(pts: Pt[]): Pt | null {
  if (!pts.length) return null
  return {
    x: pts.reduce((a, p) => a + p.x, 0) / pts.length,
    y: pts.reduce((a, p) => a + p.y, 0) / pts.length,
  }
}
