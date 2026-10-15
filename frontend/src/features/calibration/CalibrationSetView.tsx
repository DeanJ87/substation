// One raw calibration set (spec 002 US2, US3): a contact sheet with each frame's QA verdict and reason, the
// option to override, and the master SubStation built from it, with its method, the frames left out and, for
// flats, the falloff per corner, the radial profile and a dust-mote map.
import { Glance } from '../../components/Glance'
import { getRouteApi, Link, useNavigate } from '@tanstack/react-router'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { api, unwrap } from '../../api/client'
import { Zoomable } from '../../components/CloseLook'
import { useState } from 'react'
import { Collapsible } from '../../components/Collapsible'
import { LoadMore } from '../../components/LoadMore'
import { useProgressive } from '../../components/useProgressive'
import { Button, ErrorState, PageLoading } from '../../components/ui'
import { VerdictBadge, type VerdictState } from '../../components/VerdictBadge'
import { nightText, temp } from '../format'
import {
  builtPreviewUrl,
  qaThumbUrl,
  useCalibrationActions,
  useCalibrationSet,
  useLiveRefresh,
  type Built,
} from '../v2/hooks'
import v from '../v2/v2.module.css'
import s from './calibration.module.css'

const route = getRouteApi('/app/calibration/sets/$id')
const TYPE: Record<string, string> = { flat: 'Flats', dark: 'Darks', dark_flat: 'Dark flats', bias: 'Bias' }
const QA: Record<string, [VerdictState, string]> = {
  pass: ['accept', 'Pass'],
  warn: ['down', 'Check'],
  reject: ['reject', 'Rejected'],
}
const STATE: Record<string, [VerdictState, string]> = {
  queued: ['integ', 'Queued'],
  running: ['integ', 'Building'],
  done: ['accept', 'Built'],
  failed: ['reject', 'Failed'],
  blocked: ['await', 'Blocked'],
}
const pct = (x: number | null | undefined, digits = 1) => (x == null ? '—' : `${(x * 100).toFixed(digits)}%`)

export function CalibrationSetView() {
  useLiveRefresh()
  const id = Number(route.useParams().id)
  const q = useCalibrationSet(id)
  const act = useCalibrationActions()
  // hundreds of thumbnails: a slice at a time, inside their own scrolling pane
  const frames = useProgressive(q.data?.frames ?? [], 60, id)
  if (q.isError)
    return (
      <ErrorState title="Couldn't load this calibration set" onRetry={() => q.refetch()}>
        {q.error.message}
      </ErrorState>
    )
  const d = q.data
  if (!d) return <PageLoading />
  const latest = d.builds[0] as Built | undefined
  const busy = latest && (latest.state === 'queued' || latest.state === 'running')
  return (
    <div className={v.page}>
      <header className={v.head}>
        <div>
          <div className={v.crumbs}>
            <Link to="/calibration">Calibration</Link> / set #{d.id}
          </div>
          <h1>
            {TYPE[d.type] ?? d.type}
            {d.filter ? ` · ${d.filter}` : ''} · {d.exptime_s} s · {d.frame_count} frames
          </h1>
          <div className={v.sub}>
            {[d.camera, d.telescope].filter(Boolean).join(' on ')} ·{' '}
            {nightText(d.session_start_utc.slice(0, 10))}
            {d.gain != null ? ` · gain ${d.gain}` : ''}
            {d.offset != null ? ` · offset ${d.offset}` : ''}
            {d.set_temp_c != null ? ` · ${temp(d.set_temp_c)}` : ''}
          </div>
        </div>
        <div className={v.actions}>
          {d.type === 'flat' && <FlatFilter setId={d.id} current={d.filter ?? ''} />}
          <Button onClick={() => act.qa.mutate(d.id)} disabled={act.qa.isPending}>
            {act.qa.isPending ? 'Checking…' : d.qa_checked ? 'Check frames again' : 'Check frames'}
          </Button>
          <Button
            variant="primary"
            onClick={() => act.build.mutate({ id: d.id })}
            disabled={act.build.isPending || Boolean(busy)}
          >
            {act.build.isPending ? 'Building…' : latest?.state === 'done' ? 'Rebuild master' : 'Build master'}
          </Button>
        </div>
      </header>

      {d.type === 'flat' && (
        <p className={`${v.note} ${d.calibrator ? v.muted : v.warn}`}>
          {d.calibrator ? `Calibrated by ${d.calibrator_note} ${d.calibrator}.` : d.calibrator_note}
        </p>
      )}

      {latest && (
        <BuiltCard
          b={latest}
          forcing={act.build.isPending}
          onForce={() => act.build.mutate({ id: d.id, force: true })}
        />
      )}

      <Collapsible
        id="calibration-set-frames"
        title="Frames"
        meta={
          d.qa_checked
            ? Object.entries(d.qa_counts)
                .map(([k, n]) => `${n} ${QA[k]?.[1].toLowerCase() ?? k}`)
                .join(' · ')
            : `${d.frames.length} frames`
        }
      >
        {!d.qa_checked && <p className={`${v.note} ${v.muted}`}>Not checked yet. Checked on build.</p>}
        <div className={s.sheetPane}>
          <div className={s.sheet}>
            {frames.visible.map((f) => {
              const eff = f.override ?? f.verdict
              const [state, label] = (eff && QA[eff]) || (['integ', 'Not checked'] as [VerdictState, string])
              const stats = f.stats as { median?: number; mad?: number }
              return (
                <figure key={f.sha256} className={`${v.card} ${s.tile}`}>
                  <div className={s.thumb}>
                    {f.has_thumb ? (
                      <Zoomable target={{ kind: 'sub', sha: f.sha256 }} name={f.file}>
                        <img src={qaThumbUrl(f.sha256)} alt={f.file} loading="lazy" />
                      </Zoomable>
                    ) : (
                      <span>—</span>
                    )}
                  </div>
                  <figcaption>
                    <div className={s.tileHead}>
                      <VerdictBadge state={state} label={f.override ? `${label} (you)` : label} />
                      {f.verdict && (
                        <button
                          className={s.linkish}
                          onClick={() =>
                            act.override.mutate({
                              sha256s: [f.sha256],
                              verdict: f.override ? null : eff === 'reject' ? 'pass' : 'reject',
                            })
                          }
                        >
                          {f.override ? 'Undo' : eff === 'reject' ? 'Use it' : 'Leave out'}
                        </button>
                      )}
                    </div>
                    <div className={`${v.mono} ${s.file}`} title={f.file}>
                      <Glance sha={f.sha256} label={f.file}>
                        {f.file}
                      </Glance>
                    </div>
                    {stats.median != null && (
                      <div className={v.muted}>
                        median {stats.median.toFixed(0)} ADU · MAD {stats.mad?.toFixed(1)}
                      </div>
                    )}
                    {f.reason && eff !== 'pass' && <div className={v.note}>{f.reason}</div>}
                  </figcaption>
                </figure>
              )
            })}
          </div>
          <LoadMore hasMore={frames.hasMore} loading={false} onMore={frames.more} />
        </div>
      </Collapsible>
    </div>
  )
}

interface FlatReport {
  centre_adu?: number
  falloff?: Record<string, number>
  mean_falloff?: number
  edge_falloff?: number
  radial_profile?: number[]
  dust_motes?: { x: number; y: number; diameter_px: number; depth: number }[]
  dust_mote_count?: number
  stats?: { median?: number; mad?: number }
  comparison?: {
    against_file?: string
    against_date?: string | null
    kind?: 'ratio' | 'difference'
    level_change?: number
    level_change_adu?: number
    spread?: number
    changed_spots?: number
    error?: string
  }
}

const ALT = {
  master: 'The built master, auto-stretched',
  motes: 'Dust map with motes circled',
  cmp: 'New master vs previous',
}

function BuiltCard({ b, forcing, onForce }: { b: Built; forcing: boolean; onForce: () => void }) {
  const [view, setView] = useState<'master' | 'motes' | 'cmp'>(b.has_motes ? 'motes' : 'master')
  const r = b.report as FlatReport
  const [state, label] = STATE[b.state] ?? ['integ', b.state]
  const isFlat = r.falloff != null
  return (
    <Collapsible
      id="calibration-set-master"
      className={`${v.card} ${v.cardPad} ${s.built}`}
      title="Master"
      meta={
        <span className={s.builtHead}>
          <VerdictBadge state={state} label={label} />
          {b.finished_at
            ? new Date(b.finished_at).toLocaleString('en-GB', { dateStyle: 'medium', timeStyle: 'short' })
            : ''}
          {b.engine_version ? ` · Siril ${b.engine_version}` : ''}
        </span>
      }
    >
      {b.reason && <p className={`${v.note} ${b.state === 'done' ? '' : v.warn}`}>{b.reason}</p>}
      {b.state === 'blocked' && (
        <Button onClick={onForce} disabled={forcing}>
          {forcing ? 'Building…' : 'Build anyway'}
        </Button>
      )}
      {b.error && <p className={`${v.note} ${v.bad}`}>{b.error}</p>}
      {b.state === 'done' && (
        <div className={s.builtGrid}>
          <div>
            {b.has_preview && (
              <img
                className={s.builtImg}
                src={builtPreviewUrl(b.id, view === 'master' ? 'screen' : view)}
                alt={ALT[view]}
              />
            )}
            {(b.has_motes || b.has_comparison) && (
              <div className={v.pills}>
                {b.has_motes && (
                  <button className={v.pill} aria-pressed={view === 'motes'} onClick={() => setView('motes')}>
                    Dust map
                  </button>
                )}
                <button className={v.pill} aria-pressed={view === 'master'} onClick={() => setView('master')}>
                  Master
                </button>
                {b.has_comparison && (
                  <button className={v.pill} aria-pressed={view === 'cmp'} onClick={() => setView('cmp')}>
                    Vs previous
                  </button>
                )}
              </div>
            )}
            {view === 'motes' && (
              <p className={`${v.note} ${v.muted}`}>
                Flat divided by its illumination. Measured motes circled.
              </p>
            )}
          </div>
          <dl className={s.facts}>
            <dt>Method</dt>
            <dd>{b.method}</dd>
            {b.calibrated_with && (
              <>
                <dt>Calibrated with</dt>
                <dd className={v.mono}>{b.calibrated_with}</dd>
              </>
            )}
            <dt>Frames</dt>
            <dd>
              {b.frames_used} used
              {b.frames_excluded.length ? `, ${b.frames_excluded.length} left out` : ''}
            </dd>
            {r.stats?.median != null && (
              <>
                <dt>Level</dt>
                <dd className={v.mono}>
                  {r.stats.median.toFixed(0)} ADU · MAD {r.stats.mad?.toFixed(1)}
                </dd>
              </>
            )}
            {isFlat && (
              <>
                <dt>Corner falloff</dt>
                <dd className={v.mono}>
                  {Object.entries(r.falloff ?? {})
                    .map(([k, x]) => `${k.replace('_', ' ')} ${pct(x)}`)
                    .join(' · ')}
                </dd>
                <dt>Radial profile</dt>
                <dd>
                  <Profile values={r.radial_profile ?? []} />
                </dd>
                <dt>Dust motes</dt>
                <dd>
                  {r.dust_mote_count ? (
                    <>
                      {r.dust_mote_count} found, deepest:{' '}
                      <span className={v.mono}>
                        {(r.dust_motes ?? [])
                          .slice(0, 5)
                          .map((m) => `${m.diameter_px}px ${pct(m.depth)} at ${m.x},${m.y}`)
                          .join(' · ')}
                      </span>
                    </>
                  ) : (
                    'None found.'
                  )}
                </dd>
              </>
            )}
            {r.comparison && (
              <>
                <dt>Previous master</dt>
                <dd>
                  {r.comparison.error ? (
                    <span className={v.muted}>Couldn't compare: {r.comparison.error}</span>
                  ) : (
                    <>
                      <span className={v.mono}>{r.comparison.against_file}</span>
                      {r.comparison.against_date
                        ? ` (${new Date(r.comparison.against_date).toLocaleDateString('en-GB', { dateStyle: 'medium' })})`
                        : ''}
                      {r.comparison.kind === 'ratio' ? (
                        <>
                          : ratio spread {pct(r.comparison.spread, 2)}
                          {r.comparison.changed_spots
                            ? `; ${r.comparison.changed_spots} spot${r.comparison.changed_spots === 1 ? '' : 's'} changed`
                            : '; no dust changed'}
                          .
                        </>
                      ) : (
                        <>
                          : level {r.comparison.level_change_adu! >= 0 ? '+' : ''}
                          {r.comparison.level_change_adu?.toFixed(1)} ADU, spread{' '}
                          {r.comparison.spread?.toFixed(2)} ADU.
                        </>
                      )}
                    </>
                  )}
                </dd>
              </>
            )}
          </dl>
        </div>
      )}
      {b.frames_excluded.length > 0 && (
        <details className={v.note}>
          <summary>Frames left out</summary>
          <ul>
            {b.frames_excluded.map((x) => (
              <li key={String(x.sha256)}>
                <span className={v.mono}>{String(x.sha256).slice(0, 12)}</span> · {String(x.reason)}
              </li>
            ))}
          </ul>
        </details>
      )}
    </Collapsible>
  )
}

function Profile({ values }: { values: number[] }) {
  if (values.length < 2) return <span className={v.muted}>—</span>
  const w = 220
  const h = 56
  const lo = Math.min(...values, 0.6)
  const pts = values.map((y, i) => `${(i / (values.length - 1)) * w},${h - ((y - lo) / (1.02 - lo)) * h}`)
  return (
    <svg width={w} height={h} role="img" aria-label="Brightness from centre to corner">
      <polyline points={pts.join(' ')} fill="none" stroke="var(--sst-accent)" strokeWidth="2" />
      <text x={w} y={h - 2} textAnchor="end" fontSize="10" fill="var(--sst-muted)">
        {pct(values[values.length - 1] - 1, 0)} at the edge
      </text>
    </svg>
  )
}

/** Which filter these flats were taken through: a camera with no filter wheel records none, so flats shot through
 * a Duo NB read as OSC. The flats regroup with that filter's flats, and this page follows them there. */
function FlatFilter({ setId, current }: { setId: number; current: string }) {
  const qc = useQueryClient()
  const navigate = useNavigate()
  const [open, setOpen] = useState(false)
  const [value, setValue] = useState('')
  const apply = useMutation({
    mutationFn: async (filter: string) =>
      unwrap(
        await api.POST('/calibration-sets/{id}/filter', {
          params: { path: { id: setId } },
          body: { filter },
        }),
      ),
    meta: { failed: "Couldn't set the flats' filter" },
    onSuccess: (r) => {
      void qc.invalidateQueries()
      if (r.set_id && r.set_id !== setId)
        void navigate({ to: '/calibration/sets/$id', params: { id: String(r.set_id) } })
    },
  })
  if (!open)
    return (
      <Button onClick={() => setOpen(true)} disabled={apply.isPending}>
        {apply.isPending ? `Filter: ${apply.variables}…` : 'Filter…'}
      </Button>
    )
  return (
    <>
      <input
        className={v.select}
        style={{ maxWidth: 160 }}
        value={value}
        placeholder={current ? `now ${current}, e.g. Duo NB` : 'e.g. Duo NB'}
        aria-label="Filter these flats were taken through"
        onChange={(e) => setValue(e.target.value)}
      />
      <Button
        disabled={!value.trim()}
        onClick={() => {
          apply.mutate(value.trim())
          setOpen(false)
        }}
      >
        Set for these flats
      </Button>
      <Button onClick={() => setOpen(false)}>Cancel</Button>
    </>
  )
}
