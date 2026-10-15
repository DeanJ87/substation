// Dataset screen (spec 003 v2 amendment; design v2 D1–D5): header, then tabs Subs · Quality · Calibration ·
// Masters. The tab lives in the URL (?tab=), so links and reloads keep it.
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { getRouteApi, Link, useNavigate } from '@tanstack/react-router'
import { useState } from 'react'
import { api, unwrap } from '../../api/client'
import { toast } from '../../components/Toasts'
import { ErrorState, PageLoading } from '../../components/ui'
import { VerdictBadge } from '../../components/VerdictBadge'
import { nightText, temp } from '../format'
import { TargetSky } from '../sky/SkyNights'
import { useDatasetV2, useLiveRefresh, useSessions, useStacks, useSubs } from '../v2/hooks'
import v from '../v2/v2.module.css'
import { CalibrationTab } from './CalibrationTab'
import { MastersTab } from './MastersTab'
import { QualityTab } from './QualityTab'
import { isFlagged, SubsTab } from './SubsTab'

const route = getRouteApi('/app/datasets/$id')
export type Tab = 'subs' | 'quality' | 'calibration' | 'masters' | 'sky'

export function DatasetScreen() {
  useLiveRefresh()
  const { id } = route.useParams()
  const { tab = 'subs', night } = route.useSearch()
  const navigate = useNavigate()
  const dsId = Number(id)
  const ds = useDatasetV2(dsId)
  const subs = useSubs(dsId)
  const sessions = useSessions(dsId)
  const stacks = useStacks(dsId)
  if (ds.isError)
    return (
      <ErrorState title="Couldn't load this dataset" onRetry={() => ds.refetch()}>
        {ds.error.message}
      </ErrorState>
    )
  const d = ds.data
  if (!d) return <PageLoading />
  const running = (stacks.data ?? []).find((m) => m.state === 'running' || m.state === 'queued')
  const newest = [...(stacks.data ?? [])].sort((a, b) => b.version - a.version)[0]
  const failed = !running && newest?.state === 'failed' ? newest : null
  // owner 2026-10-13: the exposure should be obvious, mixed or not — "50 × 60 s, 17 × 240 s"
  const byExposure = new Map<number, number>()
  for (const x of subs.data ?? [])
    if (x.exptime_s) byExposure.set(x.exptime_s, (byExposure.get(x.exptime_s) ?? 0) + 1)
  const exposureText = [...byExposure.entries()]
    .sort((a, b) => b[1] - a[1])
    .map(([e, n]) => `${n} × ${e} s`)
    .join(', ')
  const setTab = (t: Tab) => void navigate({ to: '/datasets/$id', params: { id }, search: { tab: t } })
  const tabs: [Tab, string][] = [
    ['subs', `Subs ${d.sub_count}`],
    ['quality', 'Quality'],
    ['calibration', 'Calibration'],
    [
      'masters',
      `Masters ${(stacks.data ?? []).filter((m) => m.state !== 'failed' && m.state !== 'cancelled').length}`,
    ],
    ['sky', 'Sky'],
  ]

  // what Review was (spec 012): rejected, down-weighted or near a threshold, and not decided by hand
  const flagged = (subs.data ?? []).filter(isFlagged)
  const flaggedFirst = flagged[0]?.sha256
  const flaggedCount = flagged.length
  const firstNight = (subs.data ?? [])
    .map((x) => x.night)
    .filter((x): x is string => !!x)
    .sort()[0]
  return (
    <div className={v.page}>
      <header className={v.head}>
        <div>
          <div className={v.crumbs}>
            <Link to="/">Library</Link>
            {d.collection_id ? (
              <>
                {' / '}
                <Link to="/collections/$id" params={{ id: String(d.collection_id) }}>
                  {d.collection}
                </Link>
              </>
            ) : (
              <> / {d.target}</>
            )}
          </div>
          <h1>{d.label}</h1>
          <div className={v.sub}>
            {d.nights} session{d.nights === 1 ? '' : 's'} · {exposureText || `${d.sub_count} subs`}
            {d.gain != null && ` · gain ${d.gain}`}
            {/* nights, not UTC dates: a sub after midnight belongs to the night before (spec 012) */}
            {firstNight && ` · ${nightText(firstNight)}`}
            {d.last_night && firstNight && d.last_night !== firstNight && ` to ${nightText(d.last_night)}`}
            {d.camera && ` · ${d.camera}`}
          </div>
          {d.state_reason && (
            <div className={`${v.note} ${v.warn}`} style={{ marginTop: 6 }}>
              {d.state_reason}
            </div>
          )}
        </div>
        <div className={v.actions}>
          <Regrade id={dsId} />
          {flaggedFirst && (
            <Link
              to="/datasets/$id"
              params={{ id: String(dsId) }}
              search={{ tab: 'subs', show: 'flagged', sub: flaggedFirst }}
              className={v.pill}
            >
              Review {flaggedCount} flagged
            </Link>
          )}
          {failed && (
            <button className={v.pill} onClick={() => setTab('masters')} title={failed.error ?? ''}>
              <VerdictBadge state="reject" label={`Master v${failed.version} failed`} />
            </button>
          )}
          {running && (
            <button className={v.pill} onClick={() => setTab('masters')} aria-label="Integration in progress">
              <VerdictBadge
                state="integ"
                label={`Integrating v${running.version} · ${Math.round(running.progress * 100)}%`}
              />
            </button>
          )}
        </div>
      </header>

      <div className={v.tabs} role="tablist" aria-label="Dataset">
        {tabs.map(([t, label]) => (
          <button key={t} role="tab" aria-selected={tab === t} className={v.tab} onClick={() => setTab(t)}>
            {label}
          </button>
        ))}
      </div>

      {tab === 'subs' && <SubsTab dataset={d} subs={subs.data ?? []} sessions={sessions.data ?? []} />}
      {tab === 'quality' && (
        <QualityTab subs={subs.data ?? []} sessions={sessions.data ?? []} initialNight={night ?? null} />
      )}
      {tab === 'calibration' && (
        <CalibrationTab sessions={sessions.data ?? []} subs={subs.data ?? []} datasetId={dsId} />
      )}
      {tab === 'masters' && (
        <MastersTab dataset={d} stacks={stacks.data ?? []} sessions={sessions.data ?? []} />
      )}
      {tab === 'sky' && (
        <section className={`${v.card} ${v.cardPad}`} aria-label="The sky across nights">
          <TargetSky kind="dataset" id={dsId} />
        </section>
      )}
    </div>
  )
}

export function conditionsText(c: Record<string, number | null>): string {
  const parts = []
  if (c.sqm != null) parts.push(`SQM ${c.sqm.toFixed(2)}`)
  if (c.ambient != null) parts.push(temp(c.ambient))
  if (c.humidity != null) parts.push(`${Math.round(c.humidity)}% RH`)
  if (c.guiding != null) parts.push(`guiding ${c.guiding.toFixed(2)}″`)
  if (c.cloud != null) parts.push(`cloud ${Math.round(c.cloud)}%`)
  return parts.join(' · ')
}

/** Re-grade with the current thresholds (003-DR-01/02): first says what would change, then asks. */
function Regrade({ id }: { id: number }) {
  const qc = useQueryClient()
  const [preview, setPreview] = useState<{ changes: number; by_change: Record<string, number> } | null>(null)
  const call = useMutation({
    mutationFn: async (confirm: boolean) =>
      unwrap(await api.POST('/datasets/{id}/regrade', { params: { path: { id } }, body: { confirm } })),
    scope: { id: `regrade-${id}` },
    meta: { failed: "Couldn't re-grade" },
    onSuccess: (r) => {
      if (r.queued) {
        toast(`Re-grading ${r.changes} sub${r.changes === 1 ? '' : 's'}`)
        void qc.invalidateQueries({ queryKey: ['subs', id] })
      } else setPreview(r)
    },
  })
  if (!preview)
    return (
      <button type="button" className={v.pill} disabled={call.isPending} onClick={() => call.mutate(false)}>
        {call.isPending ? (call.variables ? 'Re-grading…' : 'Checking…') : 'Re-grade'}
      </button>
    )
  const names: Record<string, string> = { accept: 'accepted', down: 'down-weighted', reject: 'rejected' }
  const what = Object.entries(preview.by_change)
    .map(([k, n]) => {
      const [a, b] = k.split('→')
      return `${n} ${names[a] ?? a} → ${names[b] ?? b}`
    })
    .join(', ')
  return (
    <span className={v.banner} role="group" aria-label="Re-grade">
      {preview.changes === 0 ? (
        <span>No changes.</span>
      ) : (
        <span>
          {preview.changes} sub{preview.changes === 1 ? '' : 's'} would change: {what}. Manual overrides kept.
        </span>
      )}
      {preview.changes > 0 && (
        <button
          type="button"
          className={v.pill}
          onClick={() => {
            // the question goes at once; the button says Re-grading… until the server has queued it
            call.mutate(true)
            setPreview(null)
          }}
        >
          Re-grade
        </button>
      )}
      <button type="button" className={v.pill} onClick={() => setPreview(null)}>
        {preview.changes ? 'Cancel' : 'Close'}
      </button>
    </span>
  )
}
