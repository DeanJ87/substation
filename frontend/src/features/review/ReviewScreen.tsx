// Review (spec 003 v2 amendment; design v2 A2): a three-column console. Left, the flagged subs from every dataset
// grouped by session; centre, the sub with blink against the session's best sub and the session's strip; right,
// the auto grade, the sub against its own session, and the overrides. A, W and R override and move on; Shift
// applies the choice to the run of adjacent flagged subs; U reverts; J/K or the arrows step; Space blinks.
import { Glance } from '../../components/Glance'
import { Link, getRouteApi, useNavigate } from '@tanstack/react-router'
import { useEffect, useMemo, useState } from 'react'
import { EmptyState, ErrorState } from '../../components/ui'
import { VerdictIcon } from '../../components/VerdictBadge'
import { shortName, verdictState } from '../dataset/SubsTab'
import { nightText, timeText } from '../format'
import {
  fwhmText,
  num,
  previewUrl,
  useLiveRefresh,
  useReview,
  useSessions,
  useSubs,
  useVerdict,
  type Session,
  type Sub,
} from '../v2/hooks'
import v from '../v2/v2.module.css'
import s from './review.module.css'
import { CloseLook, type LookMode, Zoomable } from '../../components/CloseLook'
import { Collapsible } from '../../components/Collapsible'
import { LoadMore } from '../../components/LoadMore'
import { useProgressive } from '../../components/useProgressive'

const route = getRouteApi('/app/review')
type Group = {
  dataset_id: number
  dataset: string
  night: string | null
  rejected: number
  down: number
  near: number
  subs: Sub[]
}
type Key = 'accept' | 'keep' | 'reject' | 'auto'

const LABEL: Record<string, string> = { accept: 'Accepted', down: 'Down-weighted', reject: 'Rejected' }

/** The sharpest accepted sub of the session: what a flagged sub is blinked against. */
function bestOf(subs: Sub[]): Sub | undefined {
  const ok = subs.filter((x) => x.verdict === 'accept' && x.has_preview && (x.fwhm_arcsec ?? x.fwhm_px))
  return ok.sort((a, b) => (a.fwhm_arcsec ?? a.fwhm_px ?? 99) - (b.fwhm_arcsec ?? b.fwhm_px ?? 99))[0]
}

export function ReviewScreen() {
  useLiveRefresh()
  const { dataset } = route.useSearch()
  const q = useReview()
  const verdict = useVerdict()
  const navigate = useNavigate()
  const groups = useMemo(
    () => ((q.data ?? []) as Group[]).filter((g) => !dataset || g.dataset_id === dataset),
    [q.data, dataset],
  )
  const flat = useMemo(() => groups.flatMap((g) => g.subs.map((x) => ({ sub: x, group: g }))), [groups])
  const [sel, setSel] = useState<string | null>(null)
  const idx = Math.max(
    0,
    flat.findIndex((x) => x.sub.sha256 === sel),
  )
  const cur = flat[idx]
  const group = cur?.group
  const sessionSubs = useSubs(group?.dataset_id ?? 0)
  const sessions = useSessions(group?.dataset_id ?? 0)
  const strip = useMemo(
    () => (sessionSubs.data ?? []).filter((x) => x.night === group?.night),
    [sessionSubs.data, group?.night],
  )
  const session = (sessions.data ?? []).find((x) => x.night === group?.night)
  const best = bestOf(strip)
  const [blink, setBlink] = useState(false)
  const [showBest, setShowBest] = useState(false)
  const [actual, setActual] = useState(false)
  const [look, setLook] = useState<LookMode | null>(null)

  // the run of adjacent flagged subs in this session that the current one belongs to (Shift+A/W/R)
  const run = useMemo(() => {
    if (!cur) return []
    const flagged = new Set(group!.subs.map((x) => x.sha256))
    const i = strip.findIndex((x) => x.sha256 === cur.sub.sha256)
    if (i < 0) return [cur.sub]
    let a = i
    let b = i
    while (a > 0 && flagged.has(strip[a - 1].sha256)) a--
    while (b < strip.length - 1 && flagged.has(strip[b + 1].sha256)) b++
    return strip.slice(a, b + 1)
  }, [cur, group, strip])
  // long queues and strips load a slice at a time as they scroll, always far enough to show where you are
  const queueShown = useProgressive(groups, 60, dataset)
  const stripShown = useProgressive(strip, 120, `${group?.dataset_id}-${group?.night}`)
  const runNumbers =
    run.length > 1 ? [strip.indexOf(run[0]) + 1, strip.indexOf(run[run.length - 1]) + 1] : null

  // preload the next 20 screen previews so stepping through them is instant (003 FR-007)
  useEffect(() => {
    for (const x of flat.slice(idx + 1, idx + 21)) {
      if (x.sub.has_preview) new Image().src = previewUrl(x.sub.sha256, 'screen')
    }
  }, [flat, idx])

  const step = (d: number) => {
    const n = flat[Math.min(flat.length - 1, Math.max(0, idx + d))]
    if (n) setSel(n.sub.sha256)
  }
  const decide = (k: Key, all = false) => {
    if (!cur) return
    const shas = all ? run.map((x) => x.sha256) : [cur.sub.sha256]
    const next = flat.slice(idx + 1).find((x) => !shas.includes(x.sub.sha256))
    verdict.mutate({ sha256s: shas, verdict: k })
    if (k !== 'auto' && next) setSel(next.sub.sha256)
  }

  useEffect(() => {
    if (!blink || !best) return
    const t = window.setInterval(() => setShowBest((b) => !b), 500)
    return () => window.clearInterval(t)
  }, [blink, best])

  useEffect(() => {
    function key(e: KeyboardEvent) {
      if (look) return // the close look has its own keys
      if ((e.target as HTMLElement).closest('input, select, textarea') || e.metaKey || e.ctrlKey || e.altKey)
        return
      const k = e.key.toLowerCase()
      const map: Record<string, () => void> = {
        j: () => step(1),
        arrowright: () => step(1),
        k: () => step(-1),
        arrowleft: () => step(-1),
        a: () => decide('accept', e.shiftKey),
        w: () => decide('keep', e.shiftKey),
        r: () => decide('reject', e.shiftKey),
        u: () => decide('auto'),
        z: () => cur && setLook('full'),
        x: () => cur && setLook('inspector'),
        i: () => cur && void navigate({ to: '/subs/$sha', params: { sha: cur.sub.sha256 } }),
        ' ': () => setShowBest((b) => !b),
      }
      if (map[k]) {
        e.preventDefault()
        map[k]()
      }
    }
    window.addEventListener('keydown', key)
    return () => window.removeEventListener('keydown', key)
  })

  if (q.isError)
    return (
      <ErrorState title="Couldn't load the review list" onRetry={() => q.refetch()}>
        {q.error.message}
      </ErrorState>
    )
  if (q.isSuccess && flat.length === 0)
    return (
      <div className={v.page}>
        <h1>Review</h1>
        <EmptyState title="Nothing to review">Flagged subs appear here.</EmptyState>
      </div>
    )
  if (!cur) return null
  const sub = cur.sub
  const shown = showBest && best ? best : sub
  const posInSession = strip.findIndex((x) => x.sha256 === sub.sha256) + 1
  const wasRejected = sub.machine_verdict === 'reject'
  const queueCards = groups.slice(0, Math.max(queueShown.visible.length, groups.indexOf(group!) + 1))
  const stripThumbs = strip.slice(0, Math.max(stripShown.visible.length, posInSession + 20))

  return (
    <div className={s.console}>
      <aside className={s.queue} aria-label="To review">
        <Collapsible
          id="review-queue"
          title="To review"
          className={s.queueFold}
          meta={
            <span className={s.queueHead}>
              {flat.length.toLocaleString('en-GB')}
              {dataset && (
                <Link to="/review" search={{}} className={v.pill}>
                  All datasets
                </Link>
              )}
            </span>
          }
        >
          <div className={s.queueList}>
            {queueCards.map((g) => {
              const on = g === group
              return (
                <button
                  key={`${g.dataset_id}-${g.night}`}
                  type="button"
                  className={`${s.queueCard} ${on ? s.queueOn : ''}`}
                  onClick={() => setSel(g.subs[0].sha256)}
                >
                  <span className={s.queueTitle}>
                    {g.dataset} <span className={v.mono}>{g.subs.length}</span>
                  </span>
                  <span className={v.muted}>
                    {g.night ? nightText(g.night) : 'No night'} ·{' '}
                    {[
                      g.rejected && `${g.rejected} rejected`,
                      g.down && `${g.down} weighted`,
                      g.near && `${g.near} near`,
                    ]
                      .filter(Boolean)
                      .join(', ')}
                  </span>
                </button>
              )
            })}
            <LoadMore hasMore={queueCards.length < groups.length} loading={false} onMore={queueShown.more} />
          </div>
          <p className={`${v.muted} ${v.note}`}>Rejected, down-weighted or within 10% of a threshold.</p>
        </Collapsible>
      </aside>

      <section className={s.viewer} aria-label="Sub">
        <div className={s.viewerHead}>
          <div>
            <strong>
              {group!.dataset}
              {group!.night ? ` · ${nightText(group!.night)}` : ''}
            </strong>
            <div className={v.muted}>
              {idx + 1} / {flat.length} flagged
              {posInSession > 0 ? ` · sub ${posInSession} of ${strip.length}` : ''}
            </div>
          </div>
          <div className={v.pills}>
            <button
              type="button"
              className={v.pill}
              aria-pressed={!actual}
              onClick={() => setActual((x) => !x)}
            >
              {actual ? '1:1' : 'Fit'}
            </button>
            <button
              type="button"
              className={v.pill}
              aria-pressed={blink}
              disabled={!best || best.sha256 === sub.sha256}
              onClick={() => {
                setBlink((b) => !b)
                setShowBest(false)
              }}
            >
              Blink with best
            </button>
          </div>
        </div>
        <div className={`${s.frame} ${actual ? s.actual : ''}`}>
          {shown.has_preview ? (
            <Zoomable target={{ kind: 'sub', sha: shown.sha256 }} name={shown.file}>
              <img src={previewUrl(shown.sha256, 'screen')} alt={shown.file} />
            </Zoomable>
          ) : (
            <p className={v.muted}>No preview yet.</p>
          )}
          {showBest && best && <span className={s.blinkTag}>best of session · {shortName(best.file)}</span>}
        </div>
        <div className={v.actions}>
          <button
            type="button"
            className={v.pill}
            onClick={() => setLook('full')}
            disabled={!shown.has_preview}
          >
            100% view <kbd>Z</kbd>
          </button>
          <button
            type="button"
            className={v.pill}
            onClick={() => setLook('inspector')}
            disabled={!shown.has_preview}
          >
            Aberration inspector <kbd>X</kbd>
          </button>
        </div>
        {look && (
          <CloseLook
            target={{ kind: 'sub', sha: shown.sha256 }}
            name={shown.file}
            mode={look}
            onMode={setLook}
            onClose={() => setLook(null)}
          />
        )}
        <div className={s.fileLine}>
          <Glance sha={sub.sha256} label={sub.file}>
            <span className={v.mono}>{sub.file}</span>
          </Glance>
          <span className={v.muted}>
            {sub.time ? timeText(sub.time).slice(0, 5) : ''}
            {sub.altitude != null ? ` · alt ${Math.round(sub.altitude)}°` : ''}
          </span>
        </div>
        <div className={s.strip} aria-label="Session">
          {stripThumbs.map((x) => (
            <button
              key={x.sha256}
              type="button"
              className={`${s.thumb} ${x.sha256 === sub.sha256 ? s.thumbOn : ''}`}
              title={`${shortName(x.file)} · ${LABEL[x.verdict ?? ''] ?? 'Not graded'}`}
              onClick={() => (group!.subs.some((g) => g.sha256 === x.sha256) ? setSel(x.sha256) : undefined)}
            >
              {x.has_preview && <img src={previewUrl(x.sha256)} alt="" loading="lazy" />}
              <span className={s.disc}>
                <VerdictIcon state={verdictState(x)} size={12} title="" />
              </span>
            </button>
          ))}
          <LoadMore hasMore={stripThumbs.length < strip.length} loading={false} onMore={stripShown.more} />
        </div>
      </section>

      <aside className={s.panel} aria-label="Verdict">
        <Collapsible
          id="review-auto-grade"
          title="Auto grade"
          meta={LABEL[sub.machine_verdict ?? ''] ?? 'Not graded'}
          className={s.panelFold}
        >
          <div className={s.verdict}>
            <VerdictIcon state={verdictState({ ...sub, verdict: sub.machine_verdict })} size={20} title="" />
            <strong>{LABEL[sub.machine_verdict ?? ''] ?? 'Not graded'}</strong>
          </div>
          <p className={v.note}>{sub.reason}</p>
          <SubVsSession sub={sub} session={session} strip={strip} />
        </Collapsible>
        <div className={v.sectionLabel}>Override</div>
        <div className={s.buttons}>
          <button type="button" className={v.pill} onClick={() => decide('accept')}>
            Accept <kbd>A</kbd>
          </button>
          <button type="button" className={v.pill} onClick={() => decide('keep')}>
            Weight <kbd>W</kbd>
          </button>
          <button type="button" className={v.pill} onClick={() => decide('reject')}>
            {wasRejected ? 'Keep rejected' : 'Reject'} <kbd>R</kbd>
          </button>
        </div>
        {runNumbers && (
          <p className={`${v.muted} ${v.note}`}>
            Shift applies to subs {runNumbers[0]}–{runNumbers[1]}.
          </p>
        )}
      </aside>

      <footer className={s.legend} aria-label="Keys">
        {[
          ['J', 'next'],
          ['K', 'previous'],
          ['Space', 'blink'],
          ['A', 'accept'],
          ['W', 'down-weight'],
          ['R', 'reject'],
          ['U', 'revert to auto'],
          ['Z', '100% view'],
          ['X', 'aberration inspector'],
          ['I', 'metadata'],
          ['N', 'night vision'],
        ].map(([k, t]) => (
          <span key={k}>
            <kbd>{k}</kbd> {t}
          </span>
        ))}
      </footer>
    </div>
  )
}

function SubVsSession({ sub, session, strip }: { sub: Sub; session?: Session; strip: Sub[] }) {
  const alts = strip.map((x) => x.altitude).filter((x): x is number => x != null)
  const out = (val: number | null | undefined, p10?: number | null, p90?: number | null) =>
    val != null && p10 != null && p90 != null && (val < p10 || val > p90)
  const rows: [string, string, string, boolean][] = [
    [
      'FWHM',
      fwhmText(sub),
      session?.fwhm_arcsec.median != null ? `${session.fwhm_arcsec.median.toFixed(2)}″` : '—',
      out(sub.fwhm_arcsec, session?.fwhm_arcsec.p10, session?.fwhm_arcsec.p90),
    ],
    [
      'Stars',
      num(sub.stars),
      num(session?.stars.median),
      out(sub.stars, session?.stars.p10, session?.stars.p90),
    ],
    [
      'Background',
      num(sub.background),
      num(session?.background.median),
      out(sub.background, session?.background.p10, session?.background.p90),
    ],
    ['SQM', num(sub.sqm, 2), num(session?.sqm.median, 2), out(sub.sqm, session?.sqm.p10, session?.sqm.p90)],
    [
      'Guiding RMS',
      sub.guiding != null ? `${sub.guiding.toFixed(2)}″` : '—',
      session?.conditions.guiding != null ? `${session.conditions.guiding.toFixed(2)}″` : '—',
      sub.guiding != null &&
        session?.conditions.guiding != null &&
        sub.guiding > session.conditions.guiding * 1.5,
    ],
    [
      'Cloud',
      sub.cloud != null ? `${Math.round(sub.cloud)}%` : '—',
      session?.conditions.cloud != null ? `${Math.round(session.conditions.cloud)}%` : '—',
      (sub.cloud ?? 0) > 50,
    ],
    [
      'Altitude',
      sub.altitude != null ? `${Math.round(sub.altitude)}°` : '—',
      alts.length ? `${Math.round(Math.min(...alts))}–${Math.round(Math.max(...alts))}°` : '—',
      false,
    ],
  ]
  return (
    <table className={s.cmp}>
      <thead>
        <tr>
          <th>Measure</th>
          <th>Sub</th>
          <th>Session</th>
        </tr>
      </thead>
      <tbody>
        {rows.map(([name, a, b, bad]) => (
          <tr key={name}>
            <td>{name}</td>
            <td className={`${v.mono} ${bad ? v.warn : ''}`}>
              {a}
              {bad && <span className={s.outside}> outside the usual range</span>}
            </td>
            <td className={v.mono}>{b}</td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}
