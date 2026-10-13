// Work flyout (005-DR-01 amendment 2026-10-10): what the workers are doing, visible from every page. The header
// button names the current job and its progress; the panel lists running jobs, workers and recent failures,
// with Retry and Dismiss, and links to Activity for the full picture.
import { useQuery } from '@tanstack/react-query'
import { Link } from '@tanstack/react-router'
import { useEffect, useRef, useState } from 'react'
import { api, unwrap } from '../api/client'
import { useJobAction, type Job } from '../features/v2/hooks'
import { JobLink } from '../features/activity/Activity'
import s from './WorkFlyout.module.css'

const pct = (p: number | null | undefined) => (p == null ? '' : `${Math.round(p * 100)}%`)

export function WorkFlyout() {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)
  const q = useQuery({
    queryKey: ['activity'],
    queryFn: async () => unwrap(await api.GET('/work')),
    refetchInterval: open ? 2000 : 5000,
  })
  const act = useJobAction()
  useEffect(() => {
    if (!open) return
    const close = (e: MouseEvent | KeyboardEvent) => {
      if (e instanceof KeyboardEvent ? e.key === 'Escape' : !ref.current?.contains(e.target as Node))
        setOpen(false)
    }
    document.addEventListener('mousedown', close)
    document.addEventListener('keydown', close)
    return () => {
      document.removeEventListener('mousedown', close)
      document.removeEventListener('keydown', close)
    }
  }, [open])
  const d = q.data
  const running = d?.running ?? []
  const failed = d?.failed ?? []
  // the same job failing for the same reason shows once ("Solving failed × 361"), as on Activity
  const groups = [
    ...failed.reduce((m, j) => {
      const k = `${j.name}|${(j.error ?? '').replace(/[“"][^”"]*[”"]|\/\S+/g, '…')}`
      m.set(k, [...(m.get(k) ?? []), j])
      return m
    }, new Map<string, Job[]>()),
  ].map(([key, jobs]) => ({ key, jobs }))
  const lead = running.find((j) => j.kind !== 'ingest') ?? running[0]
  const queued = d ? Object.values(d.queue_by_kind).reduce((a, b) => a + b, 0) : 0
  const label = q.isError
    ? "Can't reach the server"
    : !d
      ? 'Loading…'
      : d.paused
        ? `Paused · ${queued.toLocaleString('en-GB')} waiting`
        : lead
          ? `${lead.name}${lead.target ? ` · ${lead.target}` : ''}`
          : 'Idle'
  return (
    <div className={s.wrap} ref={ref}>
      <button
        type="button"
        className={s.btn}
        aria-haspopup="dialog"
        aria-expanded={open}
        onClick={() => setOpen(!open)}
        title="Workers"
      >
        <span
          className={`${s.dot} ${q.isError || failed.length ? s.bad : d?.paused ? s.warn : running.length ? s.busy : s.idle}`}
          aria-hidden="true"
        />
        <span className={s.label}>{label}</span>
        {lead?.progress != null && <span className={s.pct}>{pct(lead.progress)}</span>}
        {running.length > 1 && <span className={s.more}>+{running.length - 1}</span>}
        {failed.length > 0 && (
          <span className={s.failed} aria-label={`${failed.length} failed`}>
            {failed.length}
          </span>
        )}
      </button>
      {open && d && (
        <div className={s.panel} role="dialog" aria-label="Work in progress">
          <div className={s.head}>
            <strong>Running</strong>
            <span className={s.muted}>
              {d.workers.length} worker{d.workers.length === 1 ? '' : 's'} · {queued.toLocaleString('en-GB')}{' '}
              waiting{d.paused ? ' · paused' : ''}
            </span>
          </div>
          {running.length === 0 && <p className={s.muted}>Nothing running.</p>}
          {running.slice(0, 6).map((j) => (
            <RunningRow key={j.id} j={j} />
          ))}
          {running.length > 6 && <p className={s.muted}>and {running.length - 6} more on Activity.</p>}
          {failed.length > 0 && (
            <>
              <div className={s.head}>
                <strong className={s.badText}>Failed</strong>
                <span className={s.muted}>last 2 days</span>
              </div>
              {groups.slice(0, 5).map(({ key, jobs }) => {
                const j = jobs[0]
                return (
                  <div key={key} className={s.row}>
                    <div className={s.rowTop}>
                      <span className={s.grow}>
                        {j.name} failed{jobs.length > 1 ? ` × ${jobs.length}` : ''}{' '}
                        <span className={s.muted}>
                          {jobs.length > 1 ? 'latest: ' : ''}
                          {j.target}
                        </span>
                      </span>
                      <span className={s.actions}>
                        <button
                          type="button"
                          onClick={() => jobs.forEach((x) => act.mutate({ id: x.id, action: 'retry' }))}
                        >
                          {jobs.length > 1 ? 'Retry all' : 'Retry'}
                        </button>
                        <button
                          type="button"
                          onClick={() => jobs.forEach((x) => act.mutate({ id: x.id, action: 'dismiss' }))}
                        >
                          Dismiss
                        </button>
                      </span>
                    </div>
                    <div className={s.err}>{j.error}</div>
                  </div>
                )
              })}
              {groups.length > 5 && (
                <p className={s.muted}>and {groups.length - 5} more kinds on Activity.</p>
              )}
            </>
          )}
          <Link to="/activity" className={s.all} onClick={() => setOpen(false)}>
            Open Activity
          </Link>
        </div>
      )}
    </div>
  )
}

function RunningRow({ j }: { j: Job }) {
  return (
    <div className={s.row}>
      <div className={s.rowTop}>
        <span className={s.grow} title={`${j.name} · ${j.target}`}>
          {j.link ? <JobLink href={j.link}>{j.name}</JobLink> : j.name}{' '}
          <span className={s.muted}>{j.target}</span>
        </span>
        <span className={s.pct}>{pct(j.progress)}</span>
      </div>
      <div className={s.bar}>
        <span style={{ width: `${Math.round((j.progress ?? 0) * 100)}%` }} />
      </div>
      {j.note && (
        <div className={s.note} title={j.note}>
          {j.note}
        </div>
      )}
    </div>
  )
}
