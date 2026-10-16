// A target across all its nights, from one place (spec 015 N7): the same dome as the night view with every night's
// tracks stacked on it (the latest brightest, older ones fading), a key of nights ("night 3 of 11"), and under it a
// strip of the altitudes each night's subs spanned, by date. Choosing a night brings it forward; the camera's frame
// is drawn where it pointed in the middle of that night.
import { useQuery } from '@tanstack/react-query'
import { useEffect, useRef, useState } from 'react'
import { locate, sequence } from './sequence'
import { filterTint } from '../../components/filterTint'
import { api, unwrap } from '../../api/client'
import type { components } from '../../api/schema'
import type { Scope } from '../scope/scope'
import { integrationText, shortDateText } from '../format'
import { Dome, type DomeCtx, middle } from './Dome'
import { type Pt, type Shape, DEFAULT_VIEW, SHAPES, marker, polyline, series } from './projection'
import s from './sky.module.css'
import { CameraFrame, fovText, useWidth } from './SkyView'

export type Nights = components['schemas']['NightsOut']
type Night = Nights['nights'][number]

/** `nights` narrows to the shared scope's nights (spec 018), as the collection's sessions are. */
export function useTargetSky(
  kind: 'dataset' | 'collection',
  id: number,
  site: string | null,
  nights: NightsScope = {},
) {
  return useQuery({
    queryKey: ['target-sky', kind, id, site, nights],
    queryFn: async () => {
      const query = { ...nights, site: site ?? undefined }
      return unwrap(
        kind === 'dataset'
          ? await api.GET('/datasets/{dataset_id}/sky', { params: { path: { dataset_id: id }, query } })
          : await api.GET('/collections/{collection_id}/sky', {
              params: { path: { collection_id: id }, query },
            }),
      )
    },
  })
}

/** How bright a night's tracks are: the latest full, the oldest a quarter. */
export const ageOpacity = (i: number, n: number) => (n <= 1 ? 1 : 0.25 + (0.75 * i) / (n - 1))

const placeText = (p: Nights['places'][number]) =>
  `${Math.abs(p.lat).toFixed(2)}° ${p.lat >= 0 ? 'N' : 'S'}, ${Math.abs(p.lon).toFixed(2)}° ${p.lon >= 0 ? 'E' : 'W'} · ${p.subs} subs over ${p.nights} night${p.nights === 1 ? '' : 's'}`

/** The dome across nights, loading its own data. */
type NightsScope = Pick<Scope, 'date' | 'date_from' | 'date_to'>

export function TargetSky({
  kind,
  id,
  nights,
}: {
  kind: 'dataset' | 'collection'
  id: number
  nights?: NightsScope
}) {
  const [site, setSite] = useState<string | null>(null)
  const q = useTargetSky(kind, id, site, nights)
  if (q.isError) return <p className="muted">The sky across nights couldn’t be loaded.</p>
  if (!q.data) return <p className="muted">Working out where each sub was on the sky…</p>
  return <SkyNights sky={q.data} onSite={setSite} />
}

export function SkyNights({ sky, onSite }: { sky: Nights; onSite: (key: string) => void }) {
  const [chosen, setChosen] = useState<number | null>(null)
  const [hover, setHover] = useState<number | null>(null)
  const [hiddenFilters, setHiddenFilters] = useState<Set<string>>(new Set())
  // Play: the nights end to end, the sky turning with them (owner 2026-10-15); null shows every night at once
  const [pos, setPos] = useState<number | null>(null)
  const [playing, setPlaying] = useState(false)
  const seq = sequence(sky.nights)
  const posRef = useRef(pos)
  useEffect(() => {
    posRef.current = pos
  }, [pos])
  useEffect(() => {
    if (!playing || !seq.total) return
    const reduced =
      typeof window !== 'undefined' && !!window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
    const stop = () => {
      setPlaying(false)
      setPos(null)
    }
    if (reduced) {
      const id = window.setInterval(() => {
        const next = (posRef.current ?? 0) + 30 * 60_000
        if (next >= seq.total) stop()
        else setPos(next)
      }, 700)
      return () => window.clearInterval(id)
    }
    // each night takes about five seconds, a minute at most for the lot
    const ms = Math.min(60_000, Math.max(6_000, sky.nights.length * 5_000))
    let raf = 0
    let last = performance.now()
    const tick = (now: number) => {
      const next = (posRef.current ?? 0) + ((now - last) / ms) * seq.total
      last = now
      if (next >= seq.total) return stop()
      setPos(next)
      raf = requestAnimationFrame(tick)
    }
    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
  }, [playing, seq.total, sky.nights.length])
  const n = sky.nights.length
  if (!sky.subs.length)
    return (
      <p className="muted">
        {sky.places.length
          ? `None of the ${sky.unplaced} subs from this place can be placed on the sky.`
          : 'No subs with a known place and time to put on the sky.'}
      </p>
    )
  const colour = series(0)
  // each frame's dot in its filter's colour (2026-10-16): L white, R, G, B, Hα deep red, OIII teal, SII amber
  const filters = filtersOf(sky.subs)
  const filterColour = (f: string) => filterTint(f) ?? series(filters.indexOf(f) + 1)
  const shapeOf = new Map<string, Shape>(sky.rigs.map((r, i) => [r.key, SHAPES[i % SHAPES.length]]))
  const at = pos == null ? null : locate(seq, pos)
  const lit = at ? at.night : (hover ?? chosen) // a night brought forward, else all by age
  const shownNight = at ? at.night : (chosen ?? n - 1)
  const tonight = sky.nights[shownNight]
  const t = at ? at.t : (Date.parse(tonight.first) + Date.parse(tonight.last)) / 2
  const opacity = (i: number) =>
    at ? (i === at.night ? 1 : i < at.night ? 0.18 : 0) : lit == null ? ageOpacity(i, n) : i === lit ? 1 : 0.1
  // while playing, tonight's subs appear as they were shot; nights still to come aren't drawn yet
  const shownSub = (x: { night: number; time: string; filter?: string }) =>
    !hiddenFilters.has(x.filter ?? '') &&
    (!at || x.night < at.night || (x.night === at.night && Date.parse(x.time) <= at.t))

  const draw = ({ proj, k, view }: DomeCtx) => {
    const bySeg = new Map<string, { night: number; filter: string; pts: Pt[] }>()
    for (const x of sky.subs.filter(shownSub)) {
      const key = `${x.night}:${x.dataset_id}:${x.segment}`
      const seg = bySeg.get(key) ?? { night: x.night, filter: x.filter ?? '', pts: [] }
      seg.pts.push(proj(x.alt, x.az))
      bySeg.set(key, seg)
    }
    // oldest first, so the latest (or the chosen night) is drawn on top
    const order = (i: number) => (i === lit ? n : i)
    return (
      <>
        {[...bySeg]
          .filter(([, seg]) => seg.pts.length > 1)
          .sort((a, b) => order(a[1].night) - order(b[1].night))
          .map(([key, seg]) => (
            <path
              key={key}
              d={polyline(seg.pts)}
              className={s.track}
              style={{ stroke: filterColour(seg.filter), opacity: opacity(seg.night) }}
            />
          ))}
        {sky.subs
          .filter(shownSub)
          .sort((a, b) => order(a.night) - order(b.night))
          .map((x) => (
            <path
              key={x.sha256}
              d={marker(shapeOf.get(x.rig) ?? 'circle', proj(x.alt, x.az), 3.2 / k)}
              className={s.mark}
              style={{
                fill: x.verdict === 'reject' ? 'var(--sst-panel)' : filterColour(x.filter ?? ''),
                stroke: filterColour(x.filter ?? ''),
                opacity: opacity(x.night),
                pointerEvents: 'none',
              }}
            />
          ))}
        {sky.fov && sky.lat != null && sky.lon != null && (
          <CameraFrame
            fov={sky.fov}
            lat={sky.lat}
            lon={sky.lon}
            t={t}
            view={view}
            colour={colour}
            label={`The camera’s frame, ${fovText(sky.fov)}`}
          />
        )}
      </>
    )
  }

  return (
    <div className={`${s.sky} ${s.nights}`}>
      <Dome
        lat={sky.lat}
        lon={sky.lon}
        t={t}
        spin={playing}
        label={(way) =>
          `${sky.name} on every night from one place, as a dome over the horizon facing ${way}: ${sky.subs.length} subs over ${n} night${n === 1 ? '' : 's'}, the latest brightest. The list of nights says the same.`
        }
        home={{ yaw: facingOf(sky.subs), tilt: DEFAULT_VIEW.tilt }}
        zoomTarget={(proj) =>
          middle(sky.subs.filter((x) => x.night === shownNight).map((x) => proj(x.alt, x.az)))
        }
      >
        {draw}
      </Dome>

      <div className={s.side}>
        {sky.places.length > 1 && (
          <label className={s.placePick}>
            <span className="label">From</span>
            <select value={sky.site_key ?? ''} onChange={(e) => onSite(e.target.value)}>
              {sky.places.map((p) => (
                <option key={p.key} value={p.key}>
                  {placeText(p)}
                </option>
              ))}
            </select>
          </label>
        )}
        {filters.length > 0 && (
          <div className={s.key}>
            <h3 className="label">Filters</h3>
            <ul className={s.nightKey}>
              {filters.map((f) => {
                const mine = sky.subs.filter((x) => (x.filter ?? '') === f)
                const secs = mine.reduce((a, x) => a + (x.exptime_s ?? 0), 0)
                return (
                  <li key={f}>
                    <button
                      type="button"
                      className={s.nightRow}
                      aria-pressed={!hiddenFilters.has(f)}
                      onClick={() =>
                        setHiddenFilters((h) => {
                          const next = new Set(h)
                          if (next.has(f)) next.delete(f)
                          else next.add(f)
                          return next
                        })
                      }
                    >
                      <span
                        className={s.filterDot}
                        style={{ background: filterColour(f) }}
                        aria-hidden="true"
                      />
                      <span>{f || 'No filter'}</span>
                      <span className={s.nightCount}>
                        {mine.length} · {integrationText(secs)}
                      </span>
                    </button>
                  </li>
                )
              })}
            </ul>
          </div>
        )}
        <div className={s.key}>
          <h3 className="label">Nights</h3>
          <ul className={s.nightKey}>
            {[...sky.nights].reverse().map((night) => {
              const i = sky.nights.indexOf(night)
              return (
                <li key={night.date}>
                  <button
                    type="button"
                    className={s.nightRow}
                    aria-pressed={chosen === i}
                    onClick={() => setChosen(chosen === i ? null : i)}
                    onMouseEnter={() => setHover(i)}
                    onMouseLeave={() => setHover(null)}
                    onFocus={() => setHover(i)}
                    onBlur={() => setHover(null)}
                  >
                    <span
                      className={s.nightBar}
                      style={{ background: colour, opacity: ageOpacity(i, n) }}
                      aria-hidden="true"
                    />
                    <span>
                      Night {i + 1} of {n} · {shortDateText(night.date)}
                    </span>
                    <span className={s.nightCount}>
                      {night.subs} · {integrationText(night.integration_s)}
                    </span>
                  </button>
                </li>
              )
            })}
          </ul>
          <p className={s.keyHint}>
            {sky.rigs.length > 1 && (
              <>{sky.rigs.map((r) => `${shapeName(shapeOf.get(r.key))}: ${r.name}`).join('; ')}. </>
            )}
            Choose a night to bring it forward, or play them in turn: the dome is the sky above you, so a
            target follows the same arc every night; the date only changes when it gets there, and the sky
            behind turns with the time.
            {sky.fov &&
              ` The rectangle is the camera’s frame (${fovText(sky.fov)}) ${at ? 'at the time shown' : `in the middle of ${chosen == null ? 'the latest night' : 'that night'}`}.`}
            {sky.unplaced > 0 && ` ${sky.unplaced} sub${sky.unplaced === 1 ? '' : 's'} couldn’t be placed.`}
          </p>
        </div>
      </div>

      <div className={s.play}>
        <button
          type="button"
          className={s.playButton}
          aria-pressed={playing}
          onClick={() => {
            if (!playing && (pos == null || pos >= seq.total)) setPos(0)
            setPlaying(!playing)
          }}
        >
          {playing ? 'Pause' : 'Play the nights'}
        </button>
        <input
          type="range"
          className={s.slider}
          min={0}
          max={Math.max(seq.total, 1)}
          step={60_000}
          value={pos ?? seq.total}
          aria-label="Time through the nights"
          aria-valuetext={at ? `Night ${at.night + 1} of ${n}, ${clock(at.t)}` : 'Every night'}
          onChange={(e) => {
            setPlaying(false)
            const v = Number(e.target.value)
            setPos(v >= seq.total ? null : v)
          }}
        />
        <span className={s.clock}>
          {at
            ? `Night ${at.night + 1} of ${n} · ${shortDateText(sky.nights[at.night].date)} · ${clock(at.t)}`
            : 'Every night'}
        </span>
      </div>

      <AltitudeStrip nights={sky.nights} lit={lit} colour={colour} />
    </div>
  )
}

/** Which way to face to see the target: its usual azimuth, to the nearest eighth of a turn, so a northern target
 * isn't hidden behind the dome's far wall. */
export function facingOf(subs: { az: number }[]): number {
  if (!subs.length) return DEFAULT_VIEW.yaw
  const x = subs.reduce((a, u) => a + Math.cos((u.az * Math.PI) / 180), 0)
  const y = subs.reduce((a, u) => a + Math.sin((u.az * Math.PI) / 180), 0)
  const az = ((((Math.atan2(y, x) * 180) / Math.PI) % 360) + 360) % 360
  return (Math.round(az / 45) * 45) % 360
}

const shapeName = (x: Shape | undefined) =>
  x === 'circle' || !x ? 'Circles' : `${x[0].toUpperCase()}${x.slice(1)}s`

const H = 120
const PAD = { l: 36, r: 10, t: 8, b: 22 }
const DAY = 86_400_000

/** Each night's span of altitude, by date: when in the season the target was shot, and how high (N7). */
export function AltitudeStrip({
  nights,
  lit,
  colour,
}: {
  nights: Night[]
  lit: number | null
  colour: string
}) {
  const [box, W] = useWidth<HTMLElement>(600)
  const day = (d: string) => Date.parse(`${d}T12:00:00Z`)
  const first = day(nights[0].date) - DAY
  const last = day(nights[nights.length - 1].date) + DAY
  const x = (t: number) => PAD.l + ((t - first) / (last - first)) * (W - PAD.l - PAD.r)
  const y = (alt: number) => PAD.t + (1 - Math.max(alt, 0) / 90) * (H - PAD.t - PAD.b)
  const n = nights.length
  const ticks = monthTicks(first, last)
  return (
    <figure className={s.strip} ref={box}>
      <figcaption className="label">Altitude over the dates</figcaption>
      <svg
        viewBox={`0 0 ${W} ${H}`}
        role="img"
        aria-label={`The altitudes each night’s subs spanned, from ${shortDateText(nights[0].date)} to ${shortDateText(nights[n - 1].date)}`}
      >
        {[0, 30, 60, 90].map((a) => (
          <g key={a}>
            <line x1={PAD.l} x2={W - PAD.r} y1={y(a)} y2={y(a)} className={a === 30 ? s.thirty : s.grid} />
            <text x={PAD.l - 6} y={y(a) + 4} textAnchor="end" className={s.axisText}>
              {a}°
            </text>
          </g>
        ))}
        {ticks
          .filter((_, i, all) => all.length * 64 < W || i % Math.ceil((all.length * 64) / W) === 0)
          .map((t) => (
            <text key={t} x={x(t)} y={H - 6} textAnchor="middle" className={s.axisText}>
              {new Date(t).toLocaleDateString('en-GB', { month: 'short', year: '2-digit', timeZone: 'UTC' })}
            </text>
          ))}
        {nights.map((night, i) => {
          const cx = x(day(night.date))
          return (
            <g key={night.date} style={{ opacity: lit == null ? ageOpacity(i, n) : i === lit ? 1 : 0.2 }}>
              <line
                x1={cx}
                x2={cx}
                y1={y(night.alt_min)}
                y2={y(night.alt_max)}
                className={s.stripBar}
                style={{ stroke: colour }}
              />
              <circle cx={cx} cy={y(night.alt_mid)} r={2.2} className={s.stripMid} />
            </g>
          )
        })}
      </svg>
    </figure>
  )
}

/** The first of each month across a span; at least the start, so a short span still has a label. */
export function monthTicks(start: number, end: number): number[] {
  const d = new Date(start)
  const out: number[] = []
  for (let m = Date.UTC(d.getUTCFullYear(), d.getUTCMonth() + 1, 1); m <= end;) {
    out.push(m)
    const x = new Date(m)
    m = Date.UTC(x.getUTCFullYear(), x.getUTCMonth() + 1, 1)
  }
  return out.length ? out : [start + (end - start) / 2]
}

const clock = (t: number) => new Date(t).toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' })

const FILTER_ORDER = ['L', 'R', 'G', 'B', 'Hα', 'Ha', 'OIII', 'SII']
/** The filters a target was shot in, broadband first, then narrowband, then the rest by name. */
export function filtersOf(subs: { filter?: string }[]): string[] {
  const all = [...new Set(subs.map((x) => x.filter ?? ''))]
  const rank = (f: string) => {
    const i = FILTER_ORDER.indexOf(f)
    return i < 0 ? FILTER_ORDER.length : i
  }
  return all.sort((a, b) => rank(a) - rank(b) || a.localeCompare(b))
}
