// Masters (spec 004 v2 amendment; design v2 D5): start an integration of a chosen scope and rule (with a
// preview of what it includes), the one in progress with its pipeline steps, and every version kept with its
// recipe, state and report.
import { Glance } from '../../components/Glance'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Zoomable } from '../../components/CloseLook'
import { FilePath } from '../../components/FilePath'
import { AnnotateToggle, AnnotationOverlay, useAnnotateSwitch } from '../../components/Annotations'
import { Link } from '@tanstack/react-router'
import { useState } from 'react'
import { api, unwrap } from '../../api/client'
import { Button, ConfirmButton } from '../../components/ui'
import { integrationText, nightText } from '../format'
import {
  stackPreviewUrl,
  useStackAction,
  useStartStack,
  type DatasetT,
  type Session,
  type Stack,
} from '../v2/hooks'
import { Steps } from '../steps'
import v from '../v2/v2.module.css'
import s from './dataset.module.css'
import tb from '../library/tables.module.css'
import { Collapsible } from '../../components/Collapsible'
import { LoadMore } from '../../components/LoadMore'
import { useProgressive } from '../../components/useProgressive'

type Rule = 'default' | 'accepted' | 'graded' | 'everything'
const RULES: [Rule, string][] = [
  ['default', 'Accepted and down-weighted'],
  ['accepted', 'Accepted only'],
  ['graded', 'Every graded sub'],
  ['everything', 'Everything, including rejected'],
]

export function MastersTab({
  dataset,
  stacks,
  sessions,
}: {
  dataset: DatasetT
  stacks: Stack[]
  sessions: Session[]
}) {
  const [rule, setRule] = useState<Rule>('default')
  const [nights, setNights] = useState<string[]>([])
  const [from, setFrom] = useState('')
  const [to, setTo] = useState('')
  const [partners, setPartners] = useState<number[]>([])
  const partnerList = useQuery({
    queryKey: ['stack-partners', dataset.id],
    queryFn: async () =>
      unwrap(await api.GET('/datasets/{id}/stack-partners', { params: { path: { id: dataset.id } } })),
  })
  const scope = {
    date_from: from || null,
    date_to: to || null,
    datasets: partners.length ? partners : null,
  }
  const start = useStartStack(dataset.id)
  // this master's options; empty means the defaults from Settings → Stacking (004 T016)
  const [options, setOptions] = useState<{
    rejection?: 'winsorized' | 'sigma' | 'linear'
    weighting?: 'grade' | 'snr' | 'equal'
    reference?: 'best_fwhm' | 'most_stars'
  }>({})
  const preview = useQuery({
    queryKey: ['stack-preview', dataset.id, rule, nights, from, to, partners],
    queryFn: async () =>
      unwrap(
        await api.POST('/datasets/{id}/stacks/preview', {
          params: { path: { id: dataset.id } },
          body: { rule, nights: nights.length ? nights : null, ...scope },
        }),
      ),
  })
  const running = stacks.filter((m) => m.state === 'running' || m.state === 'queued')
  const done = stacks.filter((m) => !running.includes(m))
  const p = preview.data
  const versions = useProgressive(done, 20)

  return (
    <div className={v.page}>
      <section className={`${v.card} ${v.cardPad}`}>
        <Collapsible id="masters-new" title="New master" className={s.stackForm}>
          <div className={s.formRow}>
            <label>
              <span className={v.muted}>Which subs</span>
              <select className={v.select} value={rule} onChange={(e) => setRule(e.target.value as Rule)}>
                {RULES.map(([k, l]) => (
                  <option key={k} value={k}>
                    {l}
                  </option>
                ))}
              </select>
            </label>
            <div>
              <span className={v.muted}>Sessions</span>
              <div className={`${v.pills} ${s.pillPane}`}>
                <button className={v.pill} aria-pressed={nights.length === 0} onClick={() => setNights([])}>
                  All {sessions.length}
                </button>
                {sessions.map((x) => (
                  <button
                    key={x.night}
                    className={v.pill}
                    aria-pressed={nights.includes(x.night)}
                    onClick={() =>
                      setNights(
                        nights.includes(x.night) ? nights.filter((n) => n !== x.night) : [...nights, x.night],
                      )
                    }
                  >
                    {nightText(x.night)}
                  </button>
                ))}
              </div>
            </div>
          </div>
          <div className={s.formRow}>
            <div className={v.actions}>
              <label>
                <span className={v.muted}>From</span>
                <input
                  type="date"
                  className={v.input}
                  value={from}
                  onChange={(e) => setFrom(e.target.value)}
                />
              </label>
              <label>
                <span className={v.muted}>To</span>
                <input
                  type="date"
                  className={v.input}
                  value={to}
                  min={from || undefined}
                  onChange={(e) => setTo(e.target.value)}
                />
              </label>
            </div>
            {!!partnerList.data?.length && (
              <div>
                <span className={v.muted}>Also stack</span>
                <div className={v.pills}>
                  {partnerList.data.map((d) => (
                    <button
                      key={d.id}
                      className={v.pill}
                      aria-pressed={partners.includes(d.id)}
                      onClick={() =>
                        setPartners(
                          partners.includes(d.id) ? partners.filter((x) => x !== d.id) : [...partners, d.id],
                        )
                      }
                    >
                      {d.label} · {d.subs} subs{d.collection ? ` · ${d.collection}` : ''}
                    </button>
                  ))}
                </div>
              </div>
            )}
          </div>
          <div className={s.formRow}>
            <span>
              {p ? (
                <>
                  <strong>{p.subs} subs</strong> · {integrationText(p.integration_s)} · {p.nights} session
                  {p.nights === 1 ? '' : 's'}
                  {p.excluded > 0 && <span className={v.muted}> · {p.excluded} left out</span>}
                  {p.subs > 0 && p.subs < 3 && (
                    <span className={v.muted}> · under 3 subs: no outlier rejection</span>
                  )}
                  {p.not_calibrated > 0 && (
                    <span className={v.muted}> · {p.not_calibrated} not calibrated yet</span>
                  )}
                </>
              ) : (
                '…'
              )}
            </span>
            <Button
              variant="primary"
              disabled={!p || p.subs < 2 || start.isPending}
              onClick={() => start.mutate({ rule, nights: nights.length ? nights : null, options, ...scope })}
            >
              {start.isPending
                ? 'Stacking…'
                : p && p.subs >= 2
                  ? `Stack ${p.subs.toLocaleString('en-GB')} subs`
                  : 'Stack'}
            </Button>
          </div>
          {p?.sharpness_note && <p className={`${v.note} ${v.muted}`}>{p.sharpness_note}</p>}
          <details className={s.options}>
            <summary className={v.muted}>Options</summary>
            <div className={v.actions}>
              {(
                [
                  [
                    'rejection',
                    'Rejection',
                    [
                      ['winsorized', 'Winsorised'],
                      ['sigma', 'Sigma clipping'],
                      ['linear', 'Linear fit'],
                    ],
                  ],
                  [
                    'weighting',
                    'Weighting',
                    [
                      ['grade', 'Grade'],
                      ['snr', 'SNR'],
                      ['equal', 'Equal'],
                    ],
                  ],
                  [
                    'reference',
                    'Reference',
                    [
                      ['best_fwhm', 'Best FWHM'],
                      ['most_stars', 'Most stars'],
                    ],
                  ],
                ] as const
              ).map(([key, label, choices]) => (
                <label key={key} className={v.muted}>
                  {label}{' '}
                  <select
                    className={v.select}
                    value={options[key] ?? ''}
                    onChange={(e) => setOptions({ ...options, [key]: e.target.value || undefined })}
                  >
                    <option value="">Default</option>
                    {choices.map(([value, text]) => (
                      <option key={value} value={value}>
                        {text}
                      </option>
                    ))}
                  </select>
                </label>
              ))}
            </div>
          </details>
        </Collapsible>
      </section>

      {running.map((m) => (
        <Running key={m.id} m={m} />
      ))}

      {done.length === 0 && running.length === 0 && <p className={v.empty}>No masters yet.</p>}
      {done.filter((m) => m.state !== 'failed' && m.state !== 'cancelled').length >= 2 && (
        <Compare masters={done.filter((m) => m.state !== 'failed' && m.state !== 'cancelled')} />
      )}
      {done.length > 0 && (
        <Collapsible id="masters-versions" title="Versions" meta={done.length}>
          <div className={s.versions}>
            {versions.visible.map((m) => (
              <Version key={m.id} m={m} />
            ))}
          </div>
          <LoadMore hasMore={versions.hasMore} loading={false} onMore={versions.more} />
        </Collapsible>
      )}
    </div>
  )
}

/** Compare two masters (004 T006): which is better on each measure, never on noise alone. */
function Compare({ masters }: { masters: Stack[] }) {
  const [a, setA] = useState(masters[1]?.id ?? masters[0].id)
  const [b, setB] = useState(masters[0].id)
  const q = useQuery({
    queryKey: ['stack-compare', a, b],
    enabled: a !== b,
    queryFn: async () => unwrap(await api.GET('/stacks/compare', { params: { query: { a, b } } })),
  })
  const pick = (value: number, set: (n: number) => void, label: string) => (
    <select
      className={v.select}
      aria-label={label}
      value={value}
      onChange={(e) => set(Number(e.target.value))}
    >
      {masters.map((m) => (
        <option key={m.id} value={m.id}>
          v{m.version} · {m.sub_count} subs
        </option>
      ))}
    </select>
  )
  const fmt = (x: number | null | undefined, unit: string) =>
    x == null ? '—' : `${Number.isInteger(x) ? x.toLocaleString('en-GB') : x.toFixed(2)}${unit}`
  return (
    <section className={`${v.card} ${v.cardPad}`}>
      <Collapsible id="masters-compare" title="Compare masters" defaultOpen={false}>
        <div className={v.actions}>
          {pick(a, setA, 'First master')} <span className={v.muted}>with</span>{' '}
          {pick(b, setB, 'Second master')}
        </div>
        {a === b && <p className={v.muted}>Choose two different masters.</p>}
        {q.data && (
          <>
            <p>{q.data.summary}</p>
            <table className={`${v.table} ${tb.table}`}>
              <thead>
                <tr>
                  <th>Measure</th>
                  <th className={tb.num}>{q.data.a_label}</th>
                  <th className={tb.num}>{q.data.b_label}</th>
                </tr>
              </thead>
              <tbody>
                {q.data.rows.map((r) => (
                  <tr key={r.label}>
                    <td>{r.label}</td>
                    <td className={`${v.mono} ${tb.num} ${r.better === 'a' ? v.ok : ''}`}>
                      {fmt(r.a, r.unit)}
                    </td>
                    <td className={`${v.mono} ${tb.num} ${r.better === 'b' ? v.ok : ''}`}>
                      {fmt(r.b, r.unit)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </>
        )}
        {q.error && <p className={v.bad}>{q.error.message}</p>}
      </Collapsible>
    </section>
  )
}

function Running({ m }: { m: Stack }) {
  const action = useStackAction()
  // says so on click, before the worker has noticed
  const cancelling =
    (action.isPending && action.variables.action === 'cancel') ||
    (m.state === 'running' && m.state_reason.startsWith('Cancelled'))
  return (
    <section className={`${v.card} ${s.running}`} aria-label={`Master v${m.version} integrating`}>
      <div className={s.runHead}>
        <div>
          <strong>
            Master v{m.version} · {m.state === 'queued' ? 'queued' : 'integrating'}
          </strong>
          <div className={v.muted}>
            {m.sub_count} subs from {m.session_count} session{m.session_count === 1 ? '' : 's'} ·{' '}
            {m.rule_text}
            {m.started_at &&
              ` · started ${new Date(m.started_at).toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' })}`}
          </div>
        </div>
        <div className={v.actions}>
          <Link to="/activity">Activity</Link>
          <Button disabled={cancelling} onClick={() => action.mutate({ id: m.id, action: 'cancel' })}>
            {cancelling ? 'Cancelling…' : 'Cancel'}
          </Button>
        </div>
      </div>
      <Steps
        steps={m.steps}
        step={m.step}
        cls={{
          steps: s.steps,
          step: s.step,
          bar: s.stepBar,
          fill: s.stepFill,
          done: s.stepDone,
          now: s.stepNow,
          muted: v.muted,
        }}
      />
    </section>
  )
}

const STATE_TAG: Record<string, string> = {
  current: 'Current',
  superseded: 'Superseded',
  stale: 'Stale',
  failed: 'Failed',
  cancelled: 'Cancelled',
}

/** A master's post-processing runs (spec 010), shared by its card and its stages strip. */
function usePost(id: number) {
  return useQuery({
    queryKey: ['post', id],
    queryFn: async () => unwrap(await api.GET('/stacks/{id}/post', { params: { path: { id } } })),
    refetchInterval: (query) => (query.state.data?.queued ? 5000 : false),
  })
}

function Version({ m }: { m: Stack }) {
  // owner 2026-10-12: the processed master is the master you look at; the original stack is one click away
  const post = usePost(m.id)
  const processed = [...(post.data?.runs[0]?.stages ?? [])]
    .reverse()
    .find((st) => st.state === 'done' && st.preview)
  const [showProcessed, setShowProcessed] = useState(true)
  const action = useStackAction()
  const rerunning = action.isPending && action.variables.action === 'rerun'
  const [inputs, setInputs] = useState(false)
  const members = useQuery({
    queryKey: ['stack-inputs', m.id],
    enabled: inputs,
    queryFn: async () => unwrap(await api.GET('/stacks/{id}/inputs', { params: { path: { id: m.id } } })),
  })
  const r = m.report as {
    fwhm_arcsec?: number
    fwhm_px?: number
    stars?: number
    noise?: number
    excluded_registration?: number
  }
  const stateTag =
    m.state === 'current'
      ? s.tagCurrent
      : m.state === 'failed'
        ? s.tagFailed
        : m.state === 'stale'
          ? s.tagStale
          : s.tagOld
  return (
    <section className={`${v.card} ${s.version}`}>
      <div className={s.verThumb}>
        {m.has_preview && (
          <Zoomable target={{ kind: 'master', id: m.id }} name={`Master v${m.version}`}>
            <img
              src={processed && showProcessed ? `${processed.preview}?size=thumb` : stackPreviewUrl(m.id)}
              alt={`Master v${m.version}${processed && showProcessed ? `, ${processed.label}` : ''}`}
            />
          </Zoomable>
        )}
        {processed && (
          <button
            type="button"
            className={v.pill}
            aria-pressed={showProcessed}
            title="Switch between the post-processed master and the original stack"
            onClick={() => setShowProcessed(!showProcessed)}
          >
            {showProcessed ? processed.label : 'Original'}
          </button>
        )}
      </div>
      <div>
        <strong>Master v{m.version}</strong>{' '}
        <span className={`${s.tag} ${stateTag}`}>{STATE_TAG[m.state] ?? m.state}</span>
        <div className={v.muted}>
          {m.sub_count} subs · {m.session_count} session{m.session_count === 1 ? '' : 's'} ·{' '}
          {m.finished_at
            ? new Date(m.finished_at).toLocaleString('en-GB', { dateStyle: 'medium', timeStyle: 'short' })
            : ''}{' '}
          · {m.rule_text} · {m.method}
          {m.created_by ? ` · by ${m.created_by}` : ''}
        </div>
        {(m.state_reason || m.error) && (
          <div className={`${v.note} ${m.error ? v.bad : v.muted}`}>{m.error ?? m.state_reason}</div>
        )}
      </div>
      <div className={s.verFig}>
        <span className={v.sectionLabel}>Integration</span>
        <span className={`${v.mono} ${v.accent}`}>{integrationText(m.integration_s)}</span>
      </div>
      <div className={s.verFig}>
        <span className={v.sectionLabel}>FWHM</span>
        <span className={v.mono}>
          {r.fwhm_arcsec ? `${r.fwhm_arcsec.toFixed(2)}″` : r.fwhm_px ? `${r.fwhm_px.toFixed(2)} px` : '—'}
        </span>
      </div>
      <div className={v.actions}>
        <button className={v.pill} onClick={() => setInputs(!inputs)} aria-expanded={inputs}>
          Details
        </button>
        <button
          className={v.pill}
          disabled={rerunning}
          onClick={() => action.mutate({ id: m.id, action: 'rerun' })}
        >
          {rerunning ? 'Re-running…' : 'Re-run'}
        </button>
        <ConfirmButton
          className={v.pill}
          question={<>Delete Master v{m.version}? Subs are not affected.</>}
          confirm={`Delete v${m.version}`}
          onConfirm={() => action.mutate({ id: m.id, action: 'delete' })}
        >
          Delete
        </ConfirmButton>
      </div>
      {inputs && (
        <div className={s.verFull}>
          <StackDetail id={m.id} />
          {members.data && (
            <details className={s.inputsWrap}>
              <summary className={v.muted}>{members.data.length} subs that went in or were left out</summary>
              <ul className={s.inputs}>
                {members.data.map((x) => (
                  <li key={x.sha256} className={x.included ? undefined : v.muted}>
                    <Glance sha={x.sha256} label={x.file}>
                      <Link to="/subs/$sha" params={{ sha: x.sha256 }} className={v.mono}>
                        {x.file}
                      </Link>
                    </Glance>{' '}
                    {x.included
                      ? x.weight < 1
                        ? `weight ${x.weight.toFixed(2)}`
                        : ''
                      : `left out: ${x.reason}`}
                  </li>
                ))}
              </ul>
            </details>
          )}
        </div>
      )}
      {m.state !== 'failed' && m.has_preview && <PostStages id={m.id} version={m.version} />}
    </section>
  )
}

/** How a master was made (004-DR-04). Owner 2026-10-12: the master itself, at its own shape, with switchable
 * overlays — Tilt (FWHM and roundness drawn on the corners they describe) and Annotate — and the facts beside it;
 * the calibration masters it used can be hovered and opened. */
function StackDetail({ id }: { id: number }) {
  const q = useQuery({
    queryKey: ['stack-detail', id],
    queryFn: async () => unwrap(await api.GET('/stacks/{id}/detail', { params: { path: { id } } })),
  })
  const [tilt, setTilt] = useState(true)
  const [annotate, setAnnotate] = useAnnotateSwitch()
  const d = q.data
  if (!d) return null
  const zones = (d.regional as RegionalT | undefined)?.zones ?? {}
  const hasZones = Object.values(zones).some(Boolean)
  return (
    <div className={s.detailGrid}>
      <figure className={s.detailFig}>
        <div className={v.actions}>
          {hasZones && (
            <button type="button" className={v.pill} aria-pressed={tilt} onClick={() => setTilt(!tilt)}>
              Tilt
            </button>
          )}
          <AnnotateToggle
            target={{ kind: 'master', id }}
            on={annotate}
            onChange={setAnnotate}
            className={v.pill}
          />
        </div>
        <span className={s.detailImg}>
          <Zoomable target={{ kind: 'master', id }} name={`Master ${id}`}>
            <img src={stackPreviewUrl(id)} alt="The master" />
          </Zoomable>
          {tilt && hasZones && <TiltOverlay r={d.regional as RegionalT} />}
          {annotate && <AnnotationOverlay target={{ kind: 'master', id }} />}
        </span>
        {hasZones && (d.regional as RegionalT).tilt_note && (
          <figcaption className={v.muted}>{(d.regional as RegionalT).tilt_note}</figcaption>
        )}
      </figure>
      <dl className={s.detail}>
        <dt>Method</dt>
        <dd>{d.method}</dd>
        <dt>Inputs</dt>
        <dd>
          {d.full} full · {d.weighted} weighted
          {d.left_out
            ? ` · ${d.left_out} left out (${Object.entries(d.left_out_reasons)
                .map(([r, n]) => `${n} ${r}`)
                .join(', ')})`
            : ''}
        </dd>
        {d.calibration.length > 0 && (
          <>
            <dt>Calibration</dt>
            <dd className={s.calList}>
              {d.calibration.map((c) => {
                const sha = c.sha256 as string | undefined
                const label = `${String(c.kind)} · ${String(c.file)}`
                return (
                  <div key={String(c.file)} className={s.calItem}>
                    {sha ? (
                      <Zoomable target={{ kind: 'sub', sha }} name={label}>
                        <Glance sha={sha} label={label}>
                          <span className={v.mono}>{label}</span>
                        </Glance>
                      </Zoomable>
                    ) : (
                      <span className={v.mono}>{label}</span>
                    )}
                    <span className={v.muted}> · {String(c.subs)} subs</span>
                  </div>
                )
              })}
            </dd>
          </>
        )}
        {d.notes.length > 0 && (
          <>
            <dt>Notes</dt>
            <dd>{d.notes.join(' ')}</dd>
          </>
        )}
        {d.output_path && (
          <>
            <dt>File</dt>
            <dd>
              <FilePath path={d.output_path} />
            </dd>
          </>
        )}
        {d.engine_version && (
          <>
            <dt>Engine</dt>
            <dd>{d.engine_version}</dd>
          </>
        )}
      </dl>
    </div>
  )
}

type Zone = { fwhm_px: number; roundness: number; stars: number } | null
type RegionalT = { zones: Record<string, Zone>; tilt_note: string }
// where each zone sits on the image (left, top, width, height in %): corners are the outer quarter of each side
const ZONE_BOX: Record<string, [number, number, number, number]> = {
  top_left: [0, 0, 25, 25],
  top_right: [75, 0, 25, 25],
  bottom_left: [0, 75, 25, 25],
  bottom_right: [75, 75, 25, 25],
  centre: [37.5, 37.5, 25, 25],
}

/** Tilt (004 FR-007): each zone's FWHM and roundness drawn where it was measured; the softest zone against the
 * sharpest is shaded, so a tilted sensor shows as one soft side. */
function TiltOverlay({ r }: { r: RegionalT }) {
  const vals = Object.values(r.zones)
    .filter(Boolean)
    .map((z) => z!.fwhm_px)
  const best = Math.min(...vals)
  return (
    <div className={s.tilt} aria-label="FWHM across the field">
      {Object.entries(ZONE_BOX).map(([k, [l, t, w, h]]) => {
        const z = r.zones[k]
        if (!z) return null
        const soft = z.fwhm_px / best - 1
        const tone = soft > 0.35 ? s.zoneBad : soft > 0.15 ? s.zoneWarn : s.zoneOk
        return (
          <div
            key={k}
            className={`${s.zone} ${tone}`}
            style={{ left: `${l}%`, top: `${t}%`, width: `${w}%`, height: `${h}%` }}
          >
            <span>
              {z.fwhm_px.toFixed(2)} px
              <br />
              {z.roundness.toFixed(2)} round
            </span>
          </div>
        )
      })}
    </div>
  )
}

/** Spec 010: the master's finishing stages (background extracted, deconvolved, denoised, starless), newest run,
 * each with its tool, time or the reason it was skipped. Click a stage for a bigger look. */
function PostStages({ id, version }: { id: number; version: number }) {
  const qc = useQueryClient()
  const q = usePost(id)
  const start = useMutation({
    mutationFn: async () => unwrap(await api.POST('/stacks/{id}/post', { params: { path: { id } } })),
    scope: { id: `post-${id}` },
    meta: { failed: "Couldn't start post-processing" },
    onMutate: () =>
      qc.setQueryData(['post', id], (o: object | undefined) => (o ? { ...o, queued: true } : o)),
    onSettled: () => qc.invalidateQueries({ queryKey: ['post', id] }),
  })
  const d = q.data
  if (!d) return null
  const run = d.runs[0]
  if (!run && !d.enabled && !d.queued)
    return (
      <div className={`${v.actions} ${s.postBar}`}>
        <button type="button" className={v.pill} onClick={() => start.mutate()}>
          Post-process this master
        </button>
      </div>
    )
  return (
    <div className={s.post}>
      <div className={v.actions}>
        <strong>Post-processing</strong>
        <span className={v.muted}>
          {d.queued
            ? d.helper_online
              ? `queued on ${d.helper_host}`
              : `queued · starts when a post-processing helper connects${
                  d.helper_seen_at
                    ? ` (${d.helper_host} last seen ${new Date(d.helper_seen_at).toLocaleString('en-GB', { dateStyle: 'medium', timeStyle: 'short' })})`
                    : ''
                }`
            : run
              ? `run ${run.run} · ${new Date(run.finished_at).toLocaleString('en-GB', { dateStyle: 'medium', timeStyle: 'short' })}`
              : ''}
        </span>
        <button
          type="button"
          className={v.pill}
          style={{ marginLeft: 'auto' }}
          disabled={d.queued}
          onClick={() => start.mutate()}
        >
          {run ? 'Post-process again' : 'Post-process this master'}
        </button>
      </div>
      {run && (
        <ol className={s.postStrip}>
          {run.stages.map((st, i) => (
            <li key={i} className={st.state === 'done' ? undefined : v.muted}>
              <strong>
                v{version} · {st.label}
              </strong>
              <span className={v.note}>
                {st.state === 'done' ? `${st.tool_label || 'GraXpert'} · ${st.seconds ?? 0} s` : st.reason}
              </span>
              {st.state === 'done' && st.full && (
                <Zoomable
                  target={{ kind: 'master', id }}
                  name={`Master v${version}`}
                  version={st.step}
                  className={v.pill}
                >
                  View at 100%
                </Zoomable>
              )}
              {st.file_path && <FilePath path={st.file_path} />}
            </li>
          ))}
        </ol>
      )}
    </div>
  )
}
