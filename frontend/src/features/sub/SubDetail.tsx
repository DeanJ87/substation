// Sub detail (design v2 D3): preview, verdict with reason, and every field tagged with where it came from.
// Spec 012: it opens as a modal over the list it was opened from and steps through that list (K or → next, J or ←
// previous). /subs/<sha> opens the sub's dataset with the viewer on it.
import { getRouteApi, Link, useNavigate } from '@tanstack/react-router'
import { useQuery } from '@tanstack/react-query'
import { useEffect, useState } from 'react'
import {
  Button,
  buttonClass,
  ConfirmButton,
  ErrorState,
  PageLoading,
  SegmentedControl,
} from '../../components/ui'
import { filterName } from '../../components/filters'
import { filterOfLabel } from '../../components/filterTint'
import { useBinFiles } from '../settings/Bin'
import { VerdictIcon } from '../../components/VerdictBadge'
import { clockText, countText, dateTimeText, exposureText, nightText } from '../format'
import { previewUrl, useLiveRefresh, useProcessing, useVerdict } from '../v2/hooks'
import v from '../v2/v2.module.css'
import { verdictState } from '../dataset/SubsTab'
import s from './sub.module.css'
import { CloseLook, type LookMode, Zoomable } from '../../components/CloseLook'
import { AnnotateToggle, AnnotationOverlay, useAnnotateSwitch } from '../../components/Annotations'
import { Collapsible } from '../../components/Collapsible'
import { SiteMap } from '../map/SiteMap'
import tb from '../library/tables.module.css'

const route = getRouteApi('/app/subs/$sha')

/** /subs/<sha>: the sub's dataset with the viewer open on it; a sub with no dataset is shown on its own. */
export function SubDetail() {
  const { sha } = route.useParams()
  const q = useProcessing(sha)
  const navigate = useNavigate()
  const dsId = q.data?.dataset_id
  useEffect(() => {
    if (dsId)
      void navigate({
        to: '/datasets/$id',
        params: { id: String(dsId) },
        search: { tab: 'subs', sub: sha },
        replace: true,
      })
  }, [dsId, sha, navigate])
  if (q.isError)
    return (
      <ErrorState title="Couldn't load this sub" onRetry={() => q.refetch()}>
        {q.error.message}
      </ErrorState>
    )
  if (!q.data || dsId) return <PageLoading />
  return (
    <div className={v.page}>
      <SubView sha={sha} />
    </div>
  )
}

/** Where the viewer steps: the shas of the list it was opened from, and what to call that list. */
export type SubList = {
  shas: string[]
  label: string
  onPick: (sha: string) => void
  /** when the list has nothing left to show (the last sub was binned) */
  onClose?: () => void
}
const LABEL = {
  accept: 'Accepted',
  down: 'Down-weighted',
  reject: 'Rejected',
  await: 'Awaiting calibration',
  integ: 'Not graded yet',
}

export function SubView({
  sha,
  list,
  afterVerdict,
}: {
  sha: string
  list?: SubList
  afterVerdict?: () => void
}) {
  useLiveRefresh()
  const q = useProcessing(sha)
  const bin = useBinFiles()
  const [mode, setMode] = useState<'auto' | 'stars' | 'fwhm'>('auto')
  const [look, setLook] = useState<LookMode | null>(null)
  const [annotate, setAnnotate] = useAnnotateSwitch()
  const starList = useQuery({
    queryKey: ['stars', sha],
    retry: false,
    queryFn: async () => {
      const r = await fetch(`/api/v1/frames/${sha}/stars`, { credentials: 'same-origin' })
      if (!r.ok) return null
      return (await r.json()) as StarList
    },
  })
  const navigate = useNavigate()
  const verdict = useVerdict()
  const d = q.data
  // the list it was opened from, else the dataset in capture order
  const at = list ? list.shas.indexOf(sha) : -1
  const n: { index?: number; count?: number; previous?: string; next?: string } = list
    ? {
        index: at + 1,
        count: list.shas.length,
        previous: at > 0 ? list.shas[at - 1] : undefined,
        next: at >= 0 && at < list.shas.length - 1 ? list.shas[at + 1] : undefined,
      }
    : ((d?.neighbours ?? {}) as { index?: number; count?: number; previous?: string; next?: string })
  const go = (to: string | undefined) => {
    if (!to) return
    if (list) list.onPick(to)
    else void navigate({ to: '/subs/$sha', params: { sha: to } })
  }
  const decide = (kind: 'accept' | 'keep' | 'reject' | 'auto') =>
    verdict.mutate(
      { sha256s: [sha], verdict: kind },
      { onSuccess: () => kind !== 'auto' && afterVerdict?.() },
    )
  useEffect(() => {
    function key(e: KeyboardEvent) {
      if (!d || (e.target as HTMLElement).closest('input, select, textarea') || e.metaKey || e.ctrlKey) return
      const k = e.key.toLowerCase()
      // J sits left of K: J goes back, K goes on, like ← and → (2026-10-15)
      if (k === 'k' || e.key === 'ArrowRight') go(n.next)
      else if (k === 'j' || e.key === 'ArrowLeft') go(n.previous)
      else if (k === 'a') decide('accept')
      else if (k === 'w') decide('keep')
      else if (k === 'r') decide('reject')
      else if (k === 'u') decide('auto')
      else if (k === 'z' && d.sub.has_preview) setLook('full')
      else if (k === 'x' && d.sub.has_preview) setLook('inspector')
      else return
      e.preventDefault()
    }
    window.addEventListener('keydown', key)
    return () => window.removeEventListener('keydown', key)
  })
  if (q.isError)
    return (
      <ErrorState title="Couldn't load this sub" onRetry={() => q.refetch()}>
        {q.error.message}
      </ErrorState>
    )
  if (!d) return <PageLoading />
  const sub = d.sub
  const st = verdictState(sub)
  const c = d.calibration as Record<string, string | boolean | null>
  return (
    <div className={s.view}>
      <header className={v.head}>
        <div>
          <div className={v.crumbs}>
            {d.collection_id ? (
              <Link to="/collections/$id" params={{ id: String(d.collection_id) }}>
                {d.collection}
              </Link>
            ) : (
              <Link to="/">{d.collection ?? 'Library'}</Link>
            )}
            {d.dataset_id && (
              <>
                {' / '}
                <Link to="/datasets/$id" params={{ id: String(d.dataset_id) }}>
                  {d.dataset_label ?? 'Dataset'}
                </Link>
              </>
            )}
            {sub.night && (
              <>
                {' / '}
                <Link
                  to="/datasets/$id"
                  params={{ id: String(d.dataset_id ?? '') }}
                  search={{ tab: 'quality', night: sub.night }}
                >
                  {nightText(sub.night)}
                </Link>
              </>
            )}
          </div>
          {list && <div className={v.muted}>{list.label}</div>}
          {/* the sub by what tells it apart (C23): when, through what, for how long; the file name beneath */}
          <h1>
            {[
              sub.time ? clockText(sub.time) : null,
              filterName(filterOfLabel(d.dataset_label ?? '')) || null,
              sub.exptime_s ? exposureText(sub.exptime_s) : null,
            ]
              .filter(Boolean)
              .join(' · ') || sub.file}
          </h1>
          <div className={v.muted}>
            <span className="mono" title={sub.file}>
              {sub.file}
            </span>
            {sub.time ? ` · ${dateTimeText(sub.time)}` : ' · capture time not recorded'}
          </div>
        </div>
        <div className={v.actions}>
          {n.count ? (
            <span className={v.mono}>
              {n.index} / {n.count}
            </span>
          ) : null}
          <Button disabled={!n.previous} onClick={() => go(n.previous)}>
            Previous <kbd>J</kbd>
          </Button>
          <Button disabled={!n.next} onClick={() => go(n.next)}>
            Next <kbd>K</kbd>
          </Button>
          <ConfirmButton
            variant="danger"
            question="Bin this sub?"
            confirm="Bin"
            onConfirm={() =>
              bin.mutate([sha], {
                // it's gone: the next sub, else the one before, else close (never reload the binned one)
                onSuccess: () => {
                  const to = n.next ?? n.previous
                  if (to) go(to)
                  else if (list?.onClose) list.onClose()
                  else if (d?.dataset_id != null)
                    void navigate({ to: '/datasets/$id', params: { id: String(d.dataset_id) } })
                  else void navigate({ to: '/' })
                },
              })
            }
          >
            Bin
          </ConfirmButton>
        </div>
      </header>
      <section className={`${v.card} ${tb.flush}`}>
        <Collapsible
          id="sub-raw-header"
          title="Raw FITS header"
          meta={`${Object.keys(d.raw_header).length} keywords`}
          defaultOpen={false}
        >
          <div className={tb.pane}>
            <table className={`${s.raw} ${tb.table}`}>
              <tbody>
                {Object.entries(d.raw_header).map(([k, val]) => (
                  <tr key={k}>
                    <th className={`${v.mono} ${tb.nowrap}`}>{k}</th>
                    <td className={v.mono}>{val}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Collapsible>
      </section>
      <div className={s.grid}>
        <div className={s.left}>
          {/* a view is a choice of one (segmented); tools are actions beside it (C23) */}
          <div className={s.toolbar}>
            <SegmentedControl
              label="Preview"
              size="sm"
              value={mode}
              onChange={setMode}
              options={(
                [
                  ['auto', 'Auto-stretch'],
                  ['stars', 'Stars'],
                  ['fwhm', 'FWHM map'],
                ] as const
              )
                .filter(([k]) => k === 'auto' || starList.data)
                .map(([k, label]) => ({ value: k, label }))}
            />
            <span className={v.actions}>
              <AnnotateToggle
                target={{ kind: 'sub', sha: sub.sha256 }}
                on={annotate}
                onChange={setAnnotate}
                className={buttonClass({ variant: 'ghost', size: 'sm' })}
              />
              <Button size="sm" variant="ghost" onClick={() => setLook('full')} disabled={!sub.has_preview}>
                100% view
              </Button>
              <Button
                size="sm"
                variant="ghost"
                onClick={() => setLook('inspector')}
                disabled={!sub.has_preview}
              >
                Aberration inspector
              </Button>
            </span>
          </div>
          {look && (
            <CloseLook
              target={{ kind: 'sub', sha: sub.sha256 }}
              name={sub.file}
              mode={look}
              onMode={setLook}
              onClose={() => setLook(null)}
            />
          )}
          {mode === 'stars' && (
            <p className={`${v.note} ${v.muted}`}>{countText(starList.data?.stars.length)} stars detected.</p>
          )}
          {mode === 'fwhm' && (
            <p className={`${v.note} ${v.muted}`}>
              FWHM vs median: <span className={v.ok}>sharp</span>, <span className={v.warn}>+15%</span>,{' '}
              <span className={v.bad}>+35%</span>
            </p>
          )}
          {!starList.data && !starList.isLoading && (
            <p className={`${v.note} ${v.muted}`}>No star map. Re-measure the session to create one.</p>
          )}
          <div className={s.preview}>
            {sub.has_preview ? (
              <span className={s.overlayWrap}>
                <Zoomable target={{ kind: 'sub', sha: sub.sha256 }} name={sub.file}>
                  <img src={previewUrl(sub.sha256, 'screen')} alt={`Preview of ${sub.file}`} />
                </Zoomable>
                {mode !== 'auto' && starList.data && (
                  <StarOverlay data={starList.data} fwhm={mode === 'fwhm'} />
                )}
                {annotate && <AnnotationOverlay target={{ kind: 'sub', sha: sub.sha256 }} />}
              </span>
            ) : (
              <span>No preview yet</span>
            )}
          </div>
          <section className={`${v.card} ${v.cardPad}`}>
            <div className={s.verdict}>
              <VerdictIcon state={st} size={24} title="" />
              <strong>{LABEL[st as keyof typeof LABEL]}</strong>
              <span className={v.muted}>
                {sub.manual ? 'manual' : sub.source === 'nina' ? 'NINA thumbs-down' : 'auto'}
                {d.graded_at && ` · graded ${dateTimeText(d.graded_at)}`}
              </span>
              <span className={v.actions} style={{ marginLeft: 'auto' }}>
                <Button onClick={() => decide('accept')}>
                  Accept <kbd>A</kbd>
                </Button>
                <Button onClick={() => decide('keep')}>
                  Weight <kbd>W</kbd>
                </Button>
                <Button onClick={() => decide('reject')}>
                  Reject <kbd>R</kbd>
                </Button>
              </span>
            </div>
            <p>{sub.reason ?? sub.awaiting_reason ?? sub.error ?? 'Not graded yet.'}</p>
            {d.history.length > 0 && (
              <ul className={`${v.note} ${v.muted}`}>
                {d.history.map((h, i) => (
                  <li key={i}>
                    {h.source === 'nina_bad_prefix'
                      ? 'NINA thumbs-down'
                      : `${h.verdict === 'auto' ? 'Reverted to auto' : h.verdict} by ${h.by ?? 'someone'}`}{' '}
                    · {dateTimeText(h.at)}
                  </li>
                ))}
              </ul>
            )}
          </section>
          <section className={`${v.card} ${v.cardPad}`}>
            <Collapsible
              id="sub-calibration"
              title="Calibration"
              meta={c.state === 'matched' ? (c.weak ? 'weak flat' : 'matched') : 'not matched'}
            >
              {c.state === 'matched' ? (
                <>
                  <dl className={s.fields}>
                    <div className={s.field}>
                      <dt>Dark</dt>
                      <dd>
                        {c.dark ? `${String(c.dark)} · ` : ''}
                        <span className={v.muted}>{String(c.dark_note || 'None')}</span>
                      </dd>
                    </div>
                    <div className={s.field}>
                      <dt>Flat</dt>
                      <dd>
                        {c.flat ? `${String(c.flat)} · ` : ''}
                        <span className={c.weak ? v.warn : v.muted}>{String(c.flat_note || 'None')}</span>
                      </dd>
                    </div>
                  </dl>
                  {d.dataset_id && d.sub.night ? (
                    <p className={`${v.note} ${v.muted}`}>
                      <Link
                        to="/datasets/$id"
                        params={{ id: String(d.dataset_id) }}
                        search={{ tab: 'calibration' }}
                      >
                        Change session calibration
                      </Link>
                    </p>
                  ) : null}
                </>
              ) : (
                <p className={`${v.note} ${v.warn}`}>{String(c.reason ?? 'Not matched yet.')}</p>
              )}
              {Array.isArray(c.matched_on) && (
                <details>
                  <summary className={v.muted}>Matched on</summary>
                  <dl className={s.fields}>
                    {(c.matched_on as { label: string; value: string | null; source: string }[]).map((r) => (
                      <div key={r.label} className={s.field}>
                        <dt>{r.label}</dt>
                        <dd>
                          {r.value ?? '—'} <span className={v.muted}>{r.source}</span>
                        </dd>
                      </div>
                    ))}
                  </dl>
                </details>
              )}
            </Collapsible>
          </section>
        </div>
        <div className={s.right}>
          {d.sections.map((sec) => (
            <section key={sec.title} className={`${v.card} ${tb.flush}`}>
              <Collapsible
                id={`sub-${sec.title.toLowerCase().replace(/[^a-z0-9]+/g, '-')}`}
                title={sec.title}
                meta={sec.source}
              >
                <dl className={`${s.fields} ${s.ruled}`}>
                  {sec.fields.map((f) => (
                    <div key={f.label} className={s.field}>
                      <dt>{f.label}</dt>
                      {/* where a value came from shows on hover, not on every row (C14) */}
                      <dd
                        className={f.value ? v.mono : v.muted}
                        title={f.value ? `From ${f.source}` : undefined}
                      >
                        {fieldValue(f.label, f.value)}
                      </dd>
                    </div>
                  ))}
                </dl>
              </Collapsible>
            </section>
          ))}
          {d.site_lat != null && d.site_lon != null && (
            <section className={`${v.card} ${v.cardPad}`}>
              <Collapsible id="sub-where" title="Where" meta="header">
                <SiteMap lat={d.site_lat} lon={d.site_lon} />
              </Collapsible>
            </section>
          )}
        </div>
      </div>
    </div>
  )
}

type StarList = { width: number; height: number; stars: [number, number, number, number][] }

/** Detected stars over the preview (003 G15): rings where Siril found stars, or, as an FWHM map, each star coloured
 * from sharp (ok) through soft (warn) to bloated (bad) against this sub's median. */
function StarOverlay({ data, fwhm }: { data: StarList; fwhm: boolean }) {
  const sorted = data.stars.map((x) => x[2]).sort((a, b) => a - b)
  const med = sorted[Math.floor(sorted.length / 2)] || 1
  const aspect = data.height / data.width
  return (
    <svg className={s.overlay} viewBox={`0 0 1 ${aspect}`} preserveAspectRatio="none" aria-hidden="true">
      {data.stars.map(([x, y, f], i) => {
        const r = fwhm ? Math.min(0.012, (f / data.width) * 2.5) : 0.006
        const tone = f > med * 1.35 ? 'var(--sst-bad)' : f > med * 1.15 ? 'var(--sst-warn)' : 'var(--sst-ok)'
        return fwhm ? (
          <circle key={i} cx={x} cy={y * aspect} r={r} fill={tone} fillOpacity={0.55} />
        ) : (
          <circle
            key={i}
            cx={x}
            cy={y * aspect}
            r={r}
            fill="none"
            stroke="var(--sst-chart-1)"
            strokeWidth={0.0012}
          />
        )
      })}
    </svg>
  )
}

/** A header value as people read it: filter names in their usual form ("Halpha" → Hα); an SNR below zero (a
 * calibrated frame's background) isn't a measure, so it isn't shown as one (C23). */
function fieldValue(label: string, value: string | null | undefined): string {
  if (value == null || value === '') return 'Not recorded'
  if (/^filter$/i.test(label)) return filterName(value)
  if (/snr/i.test(label) && /^[-−]/.test(value.trim())) return 'Not measurable'
  return value
}
