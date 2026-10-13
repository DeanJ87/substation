// Sub detail (design v2 D3): preview, verdict with reason, and every field tagged with where it came from;
// J and K step through the session.
import { getRouteApi, Link, useNavigate } from '@tanstack/react-router'
import { useQuery } from '@tanstack/react-query'
import { useEffect, useState } from 'react'
import { Button, ErrorState, PageLoading } from '../../components/ui'
import { VerdictIcon } from '../../components/VerdictBadge'
import { nightText } from '../format'
import { previewUrl, useLiveRefresh, useProcessing, useVerdict } from '../v2/hooks'
import v from '../v2/v2.module.css'
import { verdictState } from '../dataset/SubsTab'
import s from './sub.module.css'
import { CloseLook, type LookMode, Zoomable } from '../../components/CloseLook'
import { AnnotateToggle, AnnotationOverlay, useAnnotateSwitch } from '../../components/Annotations'
import { Collapsible } from '../../components/Collapsible'
import tb from '../library/tables.module.css'

const route = getRouteApi('/app/subs/$sha')
const LABEL = {
  accept: 'Accepted',
  down: 'Down-weighted',
  reject: 'Rejected',
  await: 'Awaiting calibration',
  integ: 'Not graded yet',
}

export function SubDetail() {
  useLiveRefresh()
  const { sha } = route.useParams()
  const q = useProcessing(sha)
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
  useEffect(() => {
    function key(e: KeyboardEvent) {
      if (!d || (e.target as HTMLElement).closest('input, select, textarea') || e.metaKey || e.ctrlKey) return
      const k = e.key.toLowerCase()
      const n = d.neighbours as { previous?: string; next?: string }
      if (k === 'j' && n.previous) void navigate({ to: '/subs/$sha', params: { sha: n.previous } })
      else if (k === 'k' && n.next) void navigate({ to: '/subs/$sha', params: { sha: n.next } })
      else if (k === 'a') verdict.mutate({ sha256s: [sha], verdict: 'accept' })
      else if (k === 'w') verdict.mutate({ sha256s: [sha], verdict: 'keep' })
      else if (k === 'r') verdict.mutate({ sha256s: [sha], verdict: 'reject' })
      else if (k === 'u') verdict.mutate({ sha256s: [sha], verdict: 'auto' })
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
  const n = d.neighbours as { index?: number; count?: number; previous?: string; next?: string }
  const st = verdictState(sub)
  const c = d.calibration as Record<string, string | boolean | null>
  return (
    <div className={v.page}>
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
          <h1 className={v.mono} style={{ fontSize: 24 }}>
            {sub.file}
          </h1>
          {/* owner 2026-10-13: when it was taken and for how long, without digging through the header */}
          <div className={v.muted}>
            {sub.time
              ? `Taken ${new Date(sub.time).toLocaleString('en-GB', { dateStyle: 'medium', timeStyle: 'short', timeZone: 'UTC' })} UTC`
              : 'Capture time not recorded'}
            {sub.exptime_s ? ` · ${sub.exptime_s} s exposure` : ''}
          </div>
        </div>
        <div className={v.actions}>
          {n.count ? (
            <span className={v.mono}>
              {n.index} / {n.count}
            </span>
          ) : null}
          <Button
            disabled={!n.previous}
            onClick={() => n.previous && navigate({ to: '/subs/$sha', params: { sha: n.previous } })}
          >
            Previous <kbd>J</kbd>
          </Button>
          <Button
            disabled={!n.next}
            onClick={() => n.next && navigate({ to: '/subs/$sha', params: { sha: n.next } })}
          >
            Next <kbd>K</kbd>
          </Button>
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
          <div className={v.pills} role="group" aria-label="Preview">
            {(
              [
                ['auto', 'Auto-stretch'],
                ['stars', 'Stars'],
                ['fwhm', 'FWHM map'],
              ] as const
            )
              .filter(([k]) => k === 'auto' || starList.data)
              .map(([k, label]) => (
                <button
                  key={k}
                  type="button"
                  className={v.pill}
                  aria-pressed={mode === k}
                  onClick={() => setMode(k)}
                >
                  {label}
                </button>
              ))}
          </div>
          <div className={v.actions}>
            <AnnotateToggle
              target={{ kind: 'sub', sha: sub.sha256 }}
              on={annotate}
              onChange={setAnnotate}
              className={v.pill}
            />
            <button
              type="button"
              className={v.pill}
              onClick={() => setLook('full')}
              disabled={!sub.has_preview}
            >
              100% view
            </button>
            <button
              type="button"
              className={v.pill}
              onClick={() => setLook('inspector')}
              disabled={!sub.has_preview}
            >
              Aberration inspector
            </button>
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
            <p className={`${v.note} ${v.muted}`}>
              {starList.data?.stars.length.toLocaleString('en-GB')} stars detected.
            </p>
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
                {d.graded_at &&
                  ` · graded ${new Date(d.graded_at).toLocaleString('en-GB', { dateStyle: 'medium', timeStyle: 'short' })}`}
              </span>
              <span className={v.actions} style={{ marginLeft: 'auto' }}>
                <Button onClick={() => verdict.mutate({ sha256s: [sha], verdict: 'accept' })}>
                  Accept <kbd>A</kbd>
                </Button>
                <Button onClick={() => verdict.mutate({ sha256s: [sha], verdict: 'keep' })}>
                  Weight <kbd>W</kbd>
                </Button>
                <Button onClick={() => verdict.mutate({ sha256s: [sha], verdict: 'reject' })}>
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
                    · {new Date(h.at).toLocaleString('en-GB', { dateStyle: 'medium', timeStyle: 'short' })}
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
                        <span className={c.dark ? v.ok : v.muted}>{String(c.dark_note || 'None')}</span>
                      </dd>
                    </div>
                    <div className={s.field}>
                      <dt>Flat</dt>
                      <dd>
                        {c.flat ? `${String(c.flat)} · ` : ''}
                        <span className={c.weak ? v.warn : c.flat ? v.ok : v.muted}>
                          {String(c.flat_note || 'None')}
                        </span>
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
                      <dd className={f.value ? v.mono : v.muted}>{f.value ?? 'Not recorded'}</dd>
                      <dd className={s.src}>{f.value ? f.source.toUpperCase() : '—'}</dd>
                    </div>
                  ))}
                </dl>
              </Collapsible>
            </section>
          ))}
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
            stroke="var(--sst-accent)"
            strokeWidth={0.0012}
          />
        )
      })}
    </svg>
  )
}
