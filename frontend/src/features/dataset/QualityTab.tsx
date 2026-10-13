// Quality (design v2 D2): every session's spread (10th–90th percentile and median) for FWHM, stars, background
// and SQM; the selected session's chart and table; an inspector for the selected sub.
import { Glance } from '../../components/Glance'
import { Link } from '@tanstack/react-router'
import { Zoomable } from '../../components/CloseLook'
import { useEffect, useMemo, useState } from 'react'
import { Button } from '../../components/ui'
import { VerdictIcon } from '../../components/VerdictBadge'
import { nightText, timeText } from '../format'
import { fwhmText, num, previewUrl, useVerdict, type Session, type Sub } from '../v2/hooks'
import v from '../v2/v2.module.css'
import s from './dataset.module.css'
import { shortName, verdictState } from './SubsTab'
import { useSort } from '../../components/sortable'
import { Collapsible } from '../../components/Collapsible'
import { LoadMore } from '../../components/LoadMore'
import { useProgressive } from '../../components/useProgressive'
import tb from '../library/tables.module.css'

const ALL = 'all'

type Metric = { key: 'fwhm' | 'stars' | 'background' | 'sqm' | 'guiding'; label: string; unit: string }
const METRICS: Metric[] = [
  { key: 'fwhm', label: 'FWHM', unit: '″' },
  { key: 'stars', label: 'Stars', unit: '' },
  { key: 'background', label: 'Background', unit: ' ADU' },
  { key: 'sqm', label: 'SQM', unit: '' },
  { key: 'guiding', label: 'Guiding RMS', unit: '″' },
]

// Design v2 D2: a fixed 620 × 56 drawing that keeps its proportions, sessions spaced evenly from oldest to newest.
const OV_W = 620
const OV_H = 56
const colW = (n: number) => Math.min(20, OV_W / Math.max(n, 1))
const colX = (i: number, n: number) => ((i + 0.5) * OV_W) / Math.max(n, 1)

/** Dates under the columns: about eight, evenly picked, with the year where it changes. */
function axisLabels(nights: string[]): { i: number; label: string }[] {
  const step = Math.max(1, Math.ceil(nights.length / 8))
  const out: { i: number; label: string }[] = []
  let year = ''
  for (let i = 0; i < nights.length; i += step) {
    const d = new Date(`${nights[i]}T12:00:00Z`)
    const y = nights[i].slice(0, 4)
    out.push({
      i,
      label: d.toLocaleDateString('en-GB', {
        day: 'numeric',
        month: 'short',
        year: y !== year ? 'numeric' : undefined,
        timeZone: 'UTC',
      }),
    })
    year = y
  }
  return out
}

function spread(sess: Session, key: Metric['key']) {
  if (key === 'fwhm') return sess.fwhm_arcsec.median != null ? sess.fwhm_arcsec : sess.fwhm_px
  if (key === 'guiding') return { median: sess.conditions.guiding ?? null, p10: null, p90: null }
  return sess[key]
}

export function QualityTab({
  subs,
  sessions,
  initialNight,
}: {
  subs: Sub[]
  sessions: Session[]
  initialNight: string | null
}) {
  // every session together by default, so a dataset's subs can be judged side by side; a column picks one night
  const [night, setNight] = useState<string>(
    initialNight ?? (sessions.length > 1 ? ALL : (sessions[0]?.night ?? ALL)),
  )
  const [selected, setSelected] = useState<string | null>(null)
  const chosen = night
  const nightSubs = useMemo(
    () => (chosen === ALL ? subs : subs.filter((x) => x.night === chosen)),
    [subs, chosen],
  )
  const current = nightSubs.find((x) => x.sha256 === selected) ?? nightSubs[0]
  const session = sessions.find((x) => x.night === (current?.night ?? chosen))
  const years = [...new Set(sessions.map((x) => x.night.slice(0, 4)))].sort().reverse()
  const [year, setYear] = useState<string | null>(null)
  // oldest first, left to right; year chips narrow a long dataset to one season (003-DR-07)
  const ordered = [...sessions].reverse().filter((x) => !year || x.night.startsWith(year))
  const verdict = useVerdict()
  const [hovered, setHovered] = useState<string | null>(null)
  const hasFocus = nightSubs.some((x) => x.focpos != null)
  const VERDICT_ORDER: Record<string, number> = { accept: 0, down: 1, reject: 2 }
  const {
    sorted: tableSubs,
    th,
    sort,
  } = useSort(nightSubs, {
    grade: (x) => VERDICT_ORDER[x.verdict ?? ''] ?? 3,
    time: (x) => x.time,
    fwhm: (x) => x.fwhm_arcsec ?? x.fwhm_px,
    stars: (x) => x.stars,
    bg: (x) => x.background,
    sqm: (x) => x.sqm,
    alt: (x) => x.altitude,
    focus: (x) => x.focpos,
    reason: (x) => x.reason ?? x.awaiting_reason,
  })
  // sorted first, then a slice at a time; a new night or sort starts again from the top
  const rows = useProgressive(tableSubs, 60, `${chosen}|${sort?.key}|${sort?.desc}`)

  return (
    <div className={v.twoCol}>
      <div className={s.quality}>
        <section className={`${v.card} ${v.cardPad}`}>
          <Collapsible id="quality-sessions" title="Sessions" meta={sessions.length}>
            <div className={s.chartHead}>
              {years.length > 1 && (
                <span className={v.pills}>
                  <button type="button" className={v.pill} aria-pressed={!year} onClick={() => setYear(null)}>
                    All
                  </button>
                  {years.map((y) => (
                    <button
                      key={y}
                      type="button"
                      className={v.pill}
                      aria-pressed={year === y}
                      onClick={() => setYear(y)}
                    >
                      {y}
                    </button>
                  ))}
                </span>
              )}
              {sessions.length > 1 && (
                <button
                  type="button"
                  className={v.pill}
                  aria-pressed={chosen === ALL}
                  onClick={() => setNight(ALL)}
                >
                  All sessions · {subs.length} subs
                </button>
              )}
            </div>
            <div className={s.overview}>
              {METRICS.map((m) => {
                const vals = ordered.map((x) => spread(x, m.key))
                const nums = vals
                  .flatMap((x) => [x.p10, x.p90, x.median])
                  .filter((x): x is number => x != null)
                const recorded = vals.filter((x) => x.median != null).length
                const all =
                  m.key === 'guiding'
                    ? vals.map((x) => x.median)
                    : subs.map((x) =>
                        m.key === 'fwhm'
                          ? (x.fwhm_arcsec ?? x.fwhm_px)
                          : m.key === 'stars'
                            ? x.stars
                            : x[m.key as 'background' | 'sqm'],
                      )
                const med = median(all.filter((x): x is number => x != null))
                const lo = Math.min(...nums)
                const hi = Math.max(...nums)
                return (
                  <div key={m.key} className={s.ovRow}>
                    <div>
                      <strong>{m.label}</strong>
                      <div className={`${v.muted} ${v.note}`}>
                        {m.key === 'sqm' || m.key === 'guiding'
                          ? `${recorded} of ${sessions.length} recorded`
                          : med != null
                            ? `median ${num(med, m.key === 'fwhm' ? 2 : 0)}${m.unit}`
                            : 'not measured yet'}
                      </div>
                    </div>
                    <svg
                      className={s.ovChart}
                      viewBox={`0 0 ${OV_W} ${OV_H}`}
                      role="img"
                      aria-label={`${m.label} per session`}
                    >
                      {vals.map((x, i) => {
                        const cx = colX(i, ordered.length)
                        const isSel = ordered[i].night === chosen
                        const flat = !Number.isFinite(lo) || hi === lo
                        const y = (val: number) =>
                          flat ? OV_H / 2 : OV_H - 4 - ((val - lo) / (hi - lo)) * (OV_H - 8)
                        const digits = m.key === 'fwhm' ? 2 : m.key === 'sqm' ? 2 : 0
                        return (
                          <g key={i} onClick={() => setNight(ordered[i].night)} className={s.ovCol}>
                            <title>
                              {x.median == null
                                ? `${nightText(ordered[i].night)}: not recorded`
                                : `${nightText(ordered[i].night)}: median ${num(x.median, digits)}${m.unit}` +
                                  (x.p10 != null && x.p90 != null
                                    ? `, 10th–90th percentile ${num(x.p10, digits)}–${num(x.p90, digits)}${m.unit}`
                                    : '')}
                            </title>
                            <rect
                              x={cx - colW(ordered.length) / 2}
                              y={0}
                              width={colW(ordered.length)}
                              height={OV_H}
                              className={isSel ? s.ovSel : s.ovHit}
                            />
                            {x.median == null ? (
                              <path
                                d={`M${cx - 3} ${OV_H / 2 - 3}l6 6M${cx + 3} ${OV_H / 2 - 3}l-6 6`}
                                className={s.ovMissing}
                              />
                            ) : (
                              <>
                                {x.p10 != null && x.p90 != null && (
                                  <rect
                                    x={cx - 2}
                                    y={Math.min(y(x.p10), y(x.p90))}
                                    width={4}
                                    height={Math.max(Math.abs(y(x.p10) - y(x.p90)), 0.5)}
                                    rx={2}
                                    className={s.ovBar}
                                  />
                                )}
                                <circle
                                  cx={cx}
                                  cy={y(x.median)}
                                  r={3}
                                  className={isSel ? s.ovDotSel : s.ovDot}
                                />
                              </>
                            )}
                          </g>
                        )
                      })}
                    </svg>
                  </div>
                )
              })}
              <div className={s.ovRow}>
                <span />
                <div className={s.ovAxis}>
                  {axisLabels(ordered.map((x) => x.night)).map((a) => (
                    <span
                      key={a.i}
                      style={{ left: `${(colX(a.i, ordered.length) / OV_W) * 100}%` }}
                      className={ordered[a.i].night === chosen ? s.ovAxisSel : undefined}
                    >
                      {a.label}
                    </span>
                  ))}
                </div>
              </div>
            </div>
          </Collapsible>
        </section>

        {nightSubs.length > 0 && (
          <section className={`${v.card} ${v.cardPad}`}>
            <Collapsible
              id="quality-chart"
              title={
                chosen === ALL
                  ? `All ${sessions.length} sessions · ${nightSubs.length} subs`
                  : `${nightText(chosen)} · ${nightSubs.length} subs`
              }
              meta={
                <span className={s.legend}>
                  <span className={s.lgFwhm}>— FWHM</span> <span className={s.lgSqm}>— SQM</span>{' '}
                  <VerdictIcon state="down" size={12} title="" /> weighted{' '}
                  <VerdictIcon state="reject" size={12} title="" /> rejected
                </span>
              }
            >
              <NightChart
                subs={nightSubs}
                onPick={setSelected}
                selected={current?.sha256 ?? null}
                bySub={chosen === ALL}
                hovered={hovered}
                onHover={setHovered}
              />
            </Collapsible>
          </section>
        )}

        <section className={`${v.card} ${tb.flush}`}>
          <Collapsible id="quality-subs" title="Subs" meta={nightSubs.length.toLocaleString('en-GB')}>
            <div className={tb.pane}>
              <table className={`${v.table} ${tb.table}`}>
                <thead>
                  <tr>
                    {th('grade', 'Grade')}
                    {th('time', 'Time', tb.nowrap)}
                    {th('fwhm', 'FWHM', tb.num)}
                    {th('stars', 'Stars', tb.num)}
                    {th('bg', 'BG', tb.num)}
                    {th('sqm', 'SQM', tb.num)}
                    {th('alt', 'Alt', tb.num)}
                    {hasFocus && th('focus', 'Focus', tb.num)}
                    {th('reason', 'Reason')}
                  </tr>
                </thead>
                <tbody>
                  {rows.visible.map((x) => (
                    <tr
                      key={x.sha256}
                      className={`${v.rowLink} ${current?.sha256 === x.sha256 || hovered === x.sha256 ? s.rowSel : ''}`}
                      onClick={() => setSelected(x.sha256)}
                      onMouseEnter={() => setHovered(x.sha256)}
                      onMouseLeave={() => setHovered(null)}
                    >
                      <td>
                        <span className={s.segment} role="group" aria-label={`Grade for ${x.file}`}>
                          {(
                            [
                              ['accept', 'keep', 'Accept'],
                              ['down', 'keep', 'Down-weight'],
                              ['reject', 'reject', 'Reject'],
                            ] as const
                          ).map(([state, , label]) => (
                            <button
                              key={state}
                              type="button"
                              aria-pressed={x.verdict === state}
                              aria-label={label}
                              title={label}
                              onClick={(e) => {
                                e.stopPropagation()
                                verdict.mutate({
                                  sha256s: [x.sha256],
                                  verdict: state === 'down' ? 'keep' : state,
                                })
                              }}
                            >
                              <VerdictIcon state={state} size={12} title="" />
                            </button>
                          ))}
                        </span>
                        {x.manual && <span className={s.manual}>M</span>}
                      </td>
                      <td className={`${v.mono} ${tb.nowrap}`}>
                        {chosen === ALL && x.night
                          ? `${new Date(`${x.night}T12:00:00Z`).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', timeZone: 'UTC' })} `
                          : ''}
                        <Glance sha={x.sha256} label={x.file}>
                          {timeText(x.time).slice(0, 5)}
                        </Glance>
                      </td>
                      <td className={`${v.mono} ${tb.num}`}>{fwhmText(x)}</td>
                      <td className={`${v.mono} ${tb.num}`}>{num(x.stars)}</td>
                      <td className={`${v.mono} ${tb.num}`}>{num(x.background)}</td>
                      <td className={`${v.mono} ${tb.num}`}>{x.sqm ? x.sqm.toFixed(2) : '—'}</td>
                      <td className={`${v.mono} ${tb.num}`}>
                        {x.altitude ? `${Math.round(x.altitude)}°` : '—'}
                      </td>
                      {hasFocus && (
                        <td className={`${v.mono} ${tb.num}`}>
                          {x.focpos != null ? Math.round(x.focpos) : '—'}
                          {x.foctemp != null && <span className={v.muted}> · {x.foctemp.toFixed(1)} °C</span>}
                        </td>
                      )}
                      <td className={v.note}>{x.reason ?? x.awaiting_reason ?? ''}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <LoadMore hasMore={rows.hasMore} loading={false} onMore={rows.more} />
            </div>
          </Collapsible>
        </section>
      </div>
      {current && <Inspector sub={current} session={session} />}
    </div>
  )
}

function median(values: number[]): number | null {
  if (!values.length) return null
  const a = [...values].sort((x, y) => x - y)
  const m = Math.floor(a.length / 2)
  return a.length % 2 ? a[m] : (a[m - 1] + a[m]) / 2
}

/** One night against the clock; with every session, subs side by side in capture order (nights apart in time
 * would otherwise leave long empty gaps), labelled by night. */
function NightChart({
  subs,
  onPick,
  selected,
  bySub = false,
  hovered = null,
  onHover = () => {},
}: {
  subs: Sub[]
  onPick: (sha: string) => void
  selected: string | null
  bySub?: boolean
  hovered?: string | null
  onHover?: (sha: string | null) => void
}) {
  const pts = subs.filter((x) => x.time)
  if (pts.length < 2) return <p className={v.muted}>Too few subs to chart.</p>
  const W = 900
  const H = 200
  const t = pts.map((x) => new Date(x.time!).getTime())
  const t0 = Math.min(...t)
  const t1 = Math.max(...t)
  const fw = pts.map((x) => x.fwhm_arcsec ?? x.fwhm_px ?? null)
  const fvals = fw.filter((x): x is number => x != null)
  const sq = pts.map((x) => x.sqm)
  const svals = sq.filter((x): x is number => x != null)
  const xOf = bySub
    ? (i: number) => 30 + (i / Math.max(1, pts.length - 1)) * (W - 60)
    : (i: number) => 30 + ((t[i] - t0) / Math.max(1, t1 - t0)) * (W - 60)
  const nightStarts = pts
    .map((x, i) => ({ i, night: x.night }))
    .filter((x, i) => i === 0 || pts[i - 1].night !== x.night)
  const every = Math.max(1, Math.ceil(nightStarts.length / 8))
  const scale = (series: number[], val: number) => {
    const lo = Math.min(...series)
    const hi = Math.max(...series)
    return 170 - ((val - lo) / Math.max(1e-9, hi - lo)) * 140
  }
  const path = (series: (number | null)[], all: number[]) =>
    series
      .map((val, i) => (val == null ? null : `${xOf(i)},${scale(all, val)}`))
      .filter(Boolean)
      .join(' ')
  const ticks = [0, 0.25, 0.5, 0.75, 1].map((f) => t0 + f * (t1 - t0))
  const medF = median(fvals)
  // per night: its own median (dashed) and its cloud passes, runs of subs with under 60% of that night's median
  // star count, shaded (003-DR-08)
  const nights = nightStarts.map((n, k) => ({
    from: n.i,
    to: (nightStarts[k + 1]?.i ?? pts.length) - 1,
  }))
  const nightMedians = nights.map((n) => {
    const vals = fw.slice(n.from, n.to + 1).filter((x): x is number => x != null)
    return { ...n, med: median(vals) }
  })
  const passes: { from: number; to: number }[] = []
  for (const n of nights) {
    const stars = pts.slice(n.from, n.to + 1).map((x) => x.stars ?? null)
    const m = median(stars.filter((x): x is number => x != null))
    if (!m) continue
    let start: number | null = null
    for (let i = n.from; i <= n.to + 1; i++) {
      const low = i <= n.to && pts[i].stars != null && pts[i].stars! < 0.6 * m
      if (low && start == null) start = i
      if (!low && start != null) {
        passes.push({ from: start, to: i - 1 })
        start = null
      }
    }
  }
  const half = (W - 60) / Math.max(1, pts.length - 1) / 2
  return (
    <svg
      viewBox={`0 0 ${W} ${H + 20}`}
      className={s.nightChart}
      role="img"
      aria-label="FWHM and SQM over the night"
    >
      {passes.map((c) => (
        <rect
          key={`c${c.from}`}
          x={xOf(c.from) - half}
          y={20}
          width={Math.max(4, xOf(c.to) - xOf(c.from) + 2 * half)}
          height={H - 20}
          className={s.cloudBand}
        >
          <title>Likely cloud · {c.to - c.from + 1} subs</title>
        </rect>
      ))}
      {bySub
        ? nightMedians.map(
            (n) =>
              n.med != null && (
                <line
                  key={`m${n.from}`}
                  x1={xOf(n.from) - half}
                  x2={xOf(n.to) + half}
                  y1={scale(fvals, n.med)}
                  y2={scale(fvals, n.med)}
                  className={s.medLine}
                />
              ),
          )
        : medF != null && (
            <line x1={30} x2={W - 30} y1={scale(fvals, medF)} y2={scale(fvals, medF)} className={s.medLine} />
          )}
      {svals.length > 1 && <polyline points={path(sq, svals)} className={s.sqmLine} />}
      {fvals.length > 1 && <polyline points={path(fw, fvals)} className={s.fwhmLine} />}
      {pts.map((x, i) => {
        const val = fw[i]
        if (val == null) return null
        const y = scale(fvals, val)
        const cls = x.verdict === 'reject' ? s.ptReject : x.verdict === 'down' ? s.ptDown : s.pt
        return (
          <g
            key={x.sha256}
            onClick={() => onPick(x.sha256)}
            onMouseEnter={() => onHover(x.sha256)}
            onMouseLeave={() => onHover(null)}
            className={s.ptHit}
          >
            <title>
              {x.night ? `${nightText(x.night)} ` : ''}
              {timeText(x.time)} · {fwhmText(x)} · {num(x.stars)} stars
            </title>
            {(x.sha256 === selected || x.sha256 === hovered) && (
              <circle cx={xOf(i)} cy={y} r={9} className={s.ptRing} />
            )}
            {x.verdict === 'reject' ? (
              <rect x={xOf(i) - 3.5} y={y - 3.5} width={7} height={7} className={cls} />
            ) : x.verdict === 'down' ? (
              <path d={`M${xOf(i) - 4} ${y - 3}h8l-4 7z`} className={cls} />
            ) : (
              <circle cx={xOf(i)} cy={y} r={3} className={cls} />
            )}
          </g>
        )
      })}
      {bySub &&
        nightStarts.map((n, k) => (
          <g key={n.i}>
            {k > 0 && <line x1={xOf(n.i) - 2} x2={xOf(n.i) - 2} y1={20} y2={H} className={s.nightSep} />}
            {k % every === 0 && n.night && (
              <text x={xOf(n.i)} y={H + 14} className={s.tick} textAnchor="start">
                {new Date(`${n.night}T12:00:00Z`).toLocaleDateString('en-GB', {
                  day: 'numeric',
                  month: 'short',
                  timeZone: 'UTC',
                })}
              </text>
            )}
          </g>
        ))}
      {!bySub &&
        ticks.map((tk) => (
          <text
            key={tk}
            x={30 + ((tk - t0) / Math.max(1, t1 - t0)) * (W - 60)}
            y={H + 14}
            className={s.tick}
            textAnchor="middle"
          >
            {new Date(tk).toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' })}
          </text>
        ))}
    </svg>
  )
}

const AUTO: Record<string, string> = { accept: 'Accepted', down: 'Down-weighted', reject: 'Rejected' }
const DID: Record<string, string> = { accept: 'accepted', down: 'down-weighted', reject: 'rejected' }

export function Inspector({ sub, session }: { sub: Sub; session?: Session }) {
  const verdict = useVerdict()
  const set = (k: 'accept' | 'keep' | 'reject' | 'auto') =>
    verdict.mutate({ sha256s: [sub.sha256], verdict: k })
  useEffect(() => {
    function key(e: KeyboardEvent) {
      if ((e.target as HTMLElement).closest('input, select, textarea') || e.metaKey || e.ctrlKey) return
      const k = e.key.toLowerCase()
      if (k === 'a') set('accept')
      else if (k === 'w') set('keep')
      else if (k === 'r') set('reject')
      else if (k === 'u') set('auto')
    }
    window.addEventListener('keydown', key)
    return () => window.removeEventListener('keydown', key)
  })
  const st = verdictState(sub)
  const label = {
    accept: 'Accepted',
    down: 'Down-weighted',
    reject: 'Rejected',
    await: 'Awaiting calibration',
    integ: 'Not graded yet',
  }[st as 'accept']
  return (
    <aside className={`${v.card} ${s.inspector}`} aria-label="Selected sub">
      <div className={s.inspPreview}>
        {sub.has_preview ? (
          <Zoomable target={{ kind: 'sub', sha: sub.sha256 }} name={sub.file}>
            <img src={previewUrl(sub.sha256, 'screen')} alt={`Preview of ${sub.file}`} />
          </Zoomable>
        ) : (
          <span>No preview</span>
        )}
        <Link to="/subs/$sha" params={{ sha: sub.sha256 }} className={v.pill}>
          Open full size
        </Link>
      </div>
      <div className={v.cardPad}>
        <div className={`${v.mono} ${v.note}`}>
          {sub.file} · {timeText(sub.time).slice(0, 5)}
        </div>
        <div className={s.inspVerdict}>
          <VerdictIcon state={st} size={22} title="" />
          <strong>{label}</strong>
          {sub.manual && <span className={s.manualTag}>MANUAL</span>}
          {sub.source === 'nina' && <span className={s.manualTag}>NINA</span>}
          {sub.provisional && <span className={s.manualTag}>PROVISIONAL</span>}
        </div>
        {sub.manual || sub.source === 'nina' ? (
          <p className={v.note}>
            Auto grade was {AUTO[sub.machine_verdict ?? ''] ?? 'not graded'}
            {sub.reason ? `: ${sub.reason}` : '.'}{' '}
            {sub.decided_by === 'NINA'
              ? 'Marked bad in NINA.'
              : `${sub.decided_by ? `${sub.decided_by} ` : 'You '}${DID[sub.verdict ?? ''] ?? 'changed'} it${
                  sub.decided_at
                    ? ` at ${new Date(sub.decided_at).toLocaleString('en-GB', { dateStyle: 'medium', timeStyle: 'short' })}`
                    : ''
                }.`}
          </p>
        ) : (
          <p className={v.note}>{sub.reason ?? sub.awaiting_reason ?? sub.error ?? 'Not graded yet.'}</p>
        )}
        <div className={v.actions}>
          <Button
            onClick={() => set('accept')}
            variant={sub.verdict === 'accept' && sub.manual ? 'primary' : 'default'}
          >
            Accept <kbd>A</kbd>
          </Button>
          <Button onClick={() => set('keep')}>
            Weight <kbd>W</kbd>
          </Button>
          <Button onClick={() => set('reject')}>
            {sub.machine_verdict === 'reject' ? 'Keep rejected' : 'Reject'} <kbd>R</kbd>
          </Button>
        </div>
        {(sub.manual || sub.source === 'nina') && (
          <button className={s.linkBtn} onClick={() => set('auto')}>
            Revert to auto grade
          </button>
        )}
        <dl className={s.kv}>
          <dt>FWHM</dt>
          <dd className={v.mono}>
            {fwhmText(sub)}
            {session?.fwhm_arcsec.median != null && (
              <span className={v.muted}> / {session.fwhm_arcsec.median.toFixed(2)}″</span>
            )}
          </dd>
          <dt>Stars</dt>
          <dd className={v.mono}>
            {num(sub.stars)}
            {session?.stars.median != null && <span className={v.muted}> / {num(session.stars.median)}</span>}
          </dd>
          <dt>Background</dt>
          <dd className={v.mono}>{num(sub.background)} ADU</dd>
          <dt>Eccentricity</dt>
          <dd className={v.mono}>{num(sub.eccentricity, 2)}</dd>
          <dt>SQM</dt>
          <dd className={v.mono}>{sub.sqm ? sub.sqm.toFixed(2) : 'Not recorded'}</dd>
          <dt>Altitude</dt>
          <dd className={v.mono}>{sub.altitude ? `${Math.round(sub.altitude)}°` : 'Not recorded'}</dd>
        </dl>
        <Link to="/subs/$sha" params={{ sha: sub.sha256 }}>
          All metadata
        </Link>
      </div>
    </aside>
  )
}

export { shortName }
