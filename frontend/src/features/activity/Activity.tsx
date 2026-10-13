// Activity (spec 005 v2 amendment; design v2 A1): what every worker is doing, what is waiting and why, recent
// results with failures pinned, host readouts, and the controls.
import { useInfiniteQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { api, unwrap } from '../../api/client'
import { Collapsible } from '../../components/Collapsible'
import { toast } from '../../components/Toasts'
import { LoadMore } from '../../components/LoadMore'
import { Link, useRouter } from '@tanstack/react-router'
import { Button, ErrorState, PageLoading, Skeleton } from '../../components/ui'
import { bytes } from '../format'
import { useActivity, useJobAction, useMoveJob, usePause, type Job, type WorkerT } from '../v2/hooks'
import { Steps } from '../steps'
import v from '../v2/v2.module.css'
import s from './activity.module.css'

function dur(sec: number | null | undefined): string {
  if (sec == null) return ''
  if (sec < 60) return `${Math.round(sec)} s`
  if (sec < 3600) return `${Math.floor(sec / 60)} min ${Math.round(sec % 60)} s`
  return `${Math.floor(sec / 3600)} h ${Math.round((sec % 3600) / 60)} min`
}
const hhmm = (iso: string | null | undefined) =>
  iso ? new Date(iso).toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' }) : ''

const PAGE = 50

/** The queue or recent results a page at a time, refreshed with the rest of the page. */
function useWorkPage(which: 'queue' | 'recent', kind?: string | null) {
  return useInfiniteQuery({
    queryKey: ['activity', which, kind ?? null],
    initialPageParam: 0,
    queryFn: async ({ pageParam }) =>
      unwrap(
        which === 'queue'
          ? await api.GET('/work/queue', {
              params: { query: { offset: pageParam, limit: PAGE, ...(kind ? { kind } : {}) } },
            })
          : await api.GET('/work/recent', { params: { query: { offset: pageParam, limit: PAGE } } }),
      ),
    getNextPageParam: (last, all) => (last.length < PAGE ? undefined : all.length * PAGE),
    refetchInterval: 4000,
  })
}

export function Activity() {
  const q = useActivity()
  const pause = usePause()
  const act = useJobAction()
  const move = useMoveJob()
  const [dragged, setDragged] = useState<string | null>(null)
  // a chip shows only that kind of job; pressing it again shows them all
  const [kind, setKind] = useState<string | null>(null)
  const queueQ = useWorkPage('queue', kind)
  const recentQ = useWorkPage('recent')
  if (q.isError)
    return (
      <ErrorState title="Couldn't load activity" onRetry={() => q.refetch()}>
        {q.error.message}
      </ErrorState>
    )
  const d = q.data
  if (!d) return <PageLoading />
  const r = d.readouts as Record<string, number | null>
  const waiting = Object.values(d.queue_by_kind).reduce((a, b) => a + b, 0)
  const memPct = r.mem_total ? ((r.mem_used ?? 0) / r.mem_total) * 100 : 0
  const used = bytes(r.mem_used)
  const total = bytes(r.mem_total)
  const free = bytes(r.disk_free)
  const write = bytes(r.disk_write_bps)
  const extra = d.readouts as Record<string, unknown>
  const workUsed = (extra.work_used ?? {}) as {
    total?: number
    calibrated?: number
    stacking?: number
    at?: string
  }
  const workBudget = (extra.work_budget_bytes as number | undefined) ?? null
  const diskNote = (d.readouts as Record<string, unknown>).disk_note as string | null | undefined
  const clearIn = (d.summary as { eta_seconds?: number | null }).eta_seconds ?? null
  const hosts = [...new Set(d.workers.filter((w) => w.kind !== 'helper').map((w) => w.host))]
  const queue = queueQ.data?.pages.flat() ?? []
  const recent = recentQ.data?.pages.flat() ?? []
  return (
    <div className={v.page}>
      <header className={v.head}>
        <div>
          <h1>Activity</h1>
          <div className={v.sub}>
            {d.workers.length} worker{d.workers.length === 1 ? '' : 's'} · {d.running.length} job
            {d.running.length === 1 ? '' : 's'} running · {waiting.toLocaleString('en-GB')} queued
            {d.paused ? ' · paused' : ''}
          </div>
        </div>
        <div className={v.actions}>
          <Button onClick={() => pause.mutate(!d.paused)} variant={d.paused ? 'primary' : 'default'}>
            {d.paused ? 'Resume new work' : 'Pause new work'}
          </Button>
          <Link to="/settings" hash="workers" className={v.pill}>
            Worker settings
          </Link>
        </div>
      </header>

      <div className={v.readouts}>
        <div className={v.readout}>
          <div className={v.readoutLabel}>
            CPU <span className={v.mono}>{Math.round(r.cpu_pct ?? 0)}%</span>
          </div>
          <div className={v.meter}>
            <span style={{ width: `${r.cpu_pct ?? 0}%` }} />
          </div>
          <div className={v.readoutDetail}>
            {r.threads} threads · {r.workers} workers
          </div>
        </div>
        <div className={v.readout}>
          <div className={v.readoutLabel}>
            Memory{' '}
            <span className={v.mono}>
              {used.value} {used.unit} / {total.value} {total.unit}
            </span>
          </div>
          <div className={v.meter}>
            <span style={{ width: `${memPct}%` }} />
          </div>
          <div className={v.readoutDetail}>
            {r.heavy_running} of {r.heavy_slots} stacking slot{r.heavy_slots === 1 ? '' : 's'} in use
          </div>
        </div>
        <div className={v.readout}>
          <div className={v.readoutLabel}>
            Disk{' '}
            <span className={v.mono}>{r.disk_write_bps != null ? `${write.value} ${write.unit}/s` : ''}</span>
          </div>
          <div className={v.meter}>
            <span style={{ width: `${r.disk_total ? (1 - (r.disk_free ?? 0) / r.disk_total) * 100 : 0}%` }} />
          </div>
          <dl className={s.kv} title={diskNote ?? undefined}>
            <dt>Free</dt>
            <dd>
              {free.value} {free.unit}
              {diskNote ? '*' : ''}
            </dd>
            {workUsed.total != null && (
              <>
                <dt>Work</dt>
                <dd title={workUsed.at ? `Measured ${hhmm(workUsed.at)}` : undefined}>
                  {bytes(workUsed.total).value} {bytes(workUsed.total).unit} of {bytes(workBudget).value}{' '}
                  {bytes(workBudget).unit}
                </dd>
                <dt>Cache</dt>
                <dd>
                  {bytes(workUsed.calibrated).value} {bytes(workUsed.calibrated).unit}
                </dd>
                {!!workUsed.stacking && (
                  <>
                    <dt>Stacking</dt>
                    <dd>
                      {bytes(workUsed.stacking).value} {bytes(workUsed.stacking).unit}
                    </dd>
                  </>
                )}
              </>
            )}
          </dl>
        </div>
        <div className={v.readout}>
          <div className={v.readoutLabel}>
            Intake <span className={v.mono}>{String(r.intake ?? 'Watching')}</span>
          </div>
          <div
            className={`${v.meter} ${['Watching', 'Scanning'].includes(String(r.intake ?? 'Watching')) ? v.meterOk : ''}`}
          >
            <span style={{ width: '100%' }} />
          </div>
          <div className={v.readoutDetail}>
            {r.folders} folder{r.folders === 1 ? '' : 's'}
            {r.last_file_at ? ` · last file ${hhmm(String(r.last_file_at))}` : ''}
          </div>
        </div>
      </div>

      <Collapsible
        id="activity-workers"
        title="Workers"
        meta={`${d.workers.filter((w) => w.job).length} of ${d.workers.length} busy`}
      >
        <div className={s.workers}>
          {d.workers.map((w) => (
            <WorkerTile key={w.id} w={w} container={hosts.indexOf(w.host) + 1} />
          ))}
        </div>
      </Collapsible>

      <Collapsible id="activity-running" title="Running" meta={d.running.length}>
        {d.running.length === 0 ? (
          <p className={v.muted}>Nothing running.</p>
        ) : (
          <div className={s.pane}>
            {d.running.map((j) => (
              <RunningJob key={j.id} j={j} />
            ))}
          </div>
        )}
      </Collapsible>

      <div className={s.cols}>
        <section className={`${v.card} ${s.colCard}`}>
          <Collapsible
            id="activity-queue"
            title="Queue"
            meta={
              <>
                {waiting.toLocaleString('en-GB')}
                {clearIn ? ` · ≈ ${dur(clearIn)}` : ''}
              </>
            }
          >
            <div className={s.chips}>
              {Object.entries(d.queue_by_kind)
                .sort((a, b) => b[1] - a[1])
                .map(([k, n]) => (
                  <button
                    key={k}
                    type="button"
                    className={s.chip}
                    aria-pressed={kind === k}
                    title={kind === k ? 'Show every kind of job' : `Show only ${k.toLowerCase()} jobs`}
                    onClick={() => setKind(kind === k ? null : k)}
                  >
                    {k} <span className={v.mono}>{n.toLocaleString('en-GB')}</span>
                  </button>
                ))}
            </div>
            <div
              className={s.pane}
              onDragOver={(e) => dragged && e.preventDefault()}
              onDrop={(e) => {
                e.preventDefault()
                const over = (e.target as HTMLElement).closest('li')?.dataset.job
                if (dragged && over && over !== dragged) move.mutate({ id: dragged, before: over })
                setDragged(null)
              }}
            >
              <ol className={s.queue}>
                {queue.map((j, i) => (
                  <li key={j.id} className={dragged === j.id ? s.dragging : undefined} data-job={j.id}>
                    <button
                      type="button"
                      className={`${v.mono} ${v.muted} ${s.handle}`}
                      aria-label={`Position ${i + 1}: ${j.name} ${j.target}. Drag, or Alt+↑/↓ to move`}
                      title="Drag, or Alt+↑/↓"
                      draggable
                      onDragStart={(e) => {
                        setDragged(j.id)
                        e.dataTransfer.effectAllowed = 'move'
                      }}
                      onDragEnd={() => setDragged(null)}
                      onKeyDown={(e) => {
                        if (!e.altKey) return
                        if (e.key === 'ArrowUp' && i > 0) move.mutate({ id: j.id, before: queue[i - 1].id })
                        else if (e.key === 'ArrowDown' && i < queue.length - 1)
                          move.mutate({ id: j.id, after: queue[i + 1].id })
                        else return
                        e.preventDefault()
                      }}
                    >
                      {i + 1}
                    </button>
                    <div className={s.rowText} title={`${j.name} · ${j.target}\n${j.wait_reason ?? ''}`}>
                      <strong>{j.name}</strong> <span className={v.muted}>{j.target}</span>
                    </div>
                    <div className={s.rowActions}>
                      <button
                        className={v.pill}
                        onClick={() =>
                          act.mutate(
                            { id: j.id, action: 'bump' },
                            // a short job then runs and leaves the queue at once: say so
                            { onSuccess: () => toast(`${j.name} runs next.`) },
                          )
                        }
                        title="Run next"
                        aria-label={`Run ${j.name} next`}
                      >
                        Run next
                      </button>
                      <button
                        className={v.pill}
                        onClick={() => act.mutate({ id: j.id, action: 'cancel' })}
                        aria-label={`Cancel ${j.name}`}
                      >
                        Cancel
                      </button>
                    </div>
                  </li>
                ))}
              </ol>
              {queueQ.isPending && <Skeleton height={120} />}
              <LoadMore
                hasMore={!!queueQ.hasNextPage}
                loading={queueQ.isFetchingNextPage}
                onMore={() => void queueQ.fetchNextPage()}
              />
            </div>
          </Collapsible>
        </section>
        <section className={`${v.card} ${s.colCard}`}>
          <Collapsible
            id="activity-recent"
            title="Recent"
            meta={d.failed.length > 0 ? <span className={v.bad}>{d.failed.length} failed</span> : undefined}
          >
            {failureGroups(d.failed).map((g) => (
              <FailureGroup key={g.key} jobs={g.jobs} act={(id, action) => act.mutate({ id, action })} />
            ))}
            <div className={s.pane}>
              <ul className={s.recent}>
                {recent.map((j) => (
                  <li key={j.id}>
                    <span className={v.ok}>✓</span>
                    <div className={s.rowText} title={`${j.name} · ${j.target}`}>
                      {j.link ? (
                        <JobLink href={j.link}>{j.outcome || `${j.name} · ${j.target}`}</JobLink>
                      ) : (
                        j.outcome || `${j.name} · ${j.target}`
                      )}
                    </div>
                    <span className={`${v.mono} ${v.muted}`}>
                      {dur(j.seconds)} · {hhmm(j.finished_at)}
                    </span>
                  </li>
                ))}
              </ul>
              {recentQ.isPending && <Skeleton height={120} />}
              <LoadMore
                hasMore={!!recentQ.hasNextPage}
                loading={recentQ.isFetchingNextPage}
                onMore={() => void recentQ.fetchNextPage()}
              />
            </div>
          </Collapsible>
        </section>
      </div>
    </div>
  )
}

/** Failures that share a job kind and cause show once ("Couldn't match calibration × 6: database is locked"),
 * so a burst of the same problem doesn't bury what's running. */
function failureGroups(failed: Job[]): { key: string; jobs: Job[] }[] {
  const groups = new Map<string, Job[]>()
  for (const j of failed) {
    const key = `${j.name}|${j.error ?? ''}`
    groups.set(key, [...(groups.get(key) ?? []), j])
  }
  return [...groups.entries()].map(([key, jobs]) => ({ key, jobs }))
}

function FailureGroup({
  jobs,
  act,
}: {
  jobs: Job[]
  act: (id: string, action: 'retry' | 'dismiss') => void
}) {
  const j = jobs[0]
  const many = jobs.length > 1
  const targets = [...new Set(jobs.map((x) => x.target).filter(Boolean))]
  return (
    <article className={s.failed}>
      <div className={s.jobHead}>
        <div>
          <strong>
            {j.name} failed
            {many ? ` × ${jobs.length}` : ''}
          </strong>{' '}
          <span className={v.muted}>
            {targets.slice(0, 3).join(', ') + (targets.length > 3 ? ` and ${targets.length - 3} more` : '')}
          </span>
          <div className={v.note}>{j.error}</div>
          <div className={`${v.note} ${v.muted}`}>
            {many ? `${jobs.length} jobs` : `Attempt ${j.attempts} of ${j.max_attempts}`}
            {j.attempts >= j.max_attempts ? ' · no more retries' : ''}
          </div>
        </div>
        <div className={v.actions}>
          <span className={v.muted}>
            {many ? `${hhmm(jobs[jobs.length - 1].finished_at)}–${hhmm(j.finished_at)}` : hhmm(j.finished_at)}
          </span>
          <Button onClick={() => jobs.forEach((x) => act(x.id, 'retry'))}>
            {many ? 'Retry all' : 'Retry'}
          </Button>
          <Button onClick={() => jobs.forEach((x) => act(x.id, 'dismiss'))}>
            {many ? 'Dismiss all' : 'Dismiss'}
          </Button>
        </div>
      </div>
      {j.log.length > 1 && (
        <details>
          <summary className={v.muted}>Details</summary>
          <pre className={s.log}>{j.log.join('\n')}</pre>
        </details>
      )}
    </article>
  )
}

/** Time left from the progress so far (005-DR-02): "≈ 9 min", only once there's enough to go on. */
function eta(j: Job): string | null {
  if (j.progress == null || j.progress < 0.05 || j.progress >= 1 || !j.seconds) return null
  const left = (j.seconds * (1 - j.progress)) / j.progress
  return left < 60
    ? '≈ 1 min'
    : left < 3600
      ? `≈ ${Math.round(left / 60)} min`
      : `≈ ${(left / 3600).toFixed(1)} h`
}

function RunningJob({ j }: { j: Job }) {
  const act = useJobAction()
  const cancelling = j.note.startsWith('Cancelling')
  const ex = j.extra as { steps?: string[]; step?: string; subs?: number; sessions?: number; why?: string }
  return (
    <article className={`${v.card} ${s.job}`}>
      <div className={s.jobHead}>
        <div className={s.jobMain}>
          <strong className={s.rowText} title={`${j.name} · ${j.target}`}>
            {j.link ? (
              <JobLink href={j.link}>{`${j.name} · ${j.target}`}</JobLink>
            ) : (
              `${j.name} · ${j.target}`
            )}
          </strong>
          <div className={`${v.muted} ${s.rowText}`}>
            {j.note || ' '}
            {ex.subs ? ` · ${ex.subs} subs from ${ex.sessions} sessions` : ''} · started {hhmm(j.started_at)}
            {ex.why ? <div className={v.muted}>{String(ex.why)}</div> : null}
          </div>
        </div>
        <div className={v.actions}>
          <span className={`${v.mono} ${v.accent}`}>
            {j.progress != null ? `${Math.round(j.progress * 100)}%` : dur(j.seconds)}
          </span>
          {eta(j) && <span className={`${v.mono} ${v.muted}`}>{eta(j)}</span>}
          {j.dataset_id && (
            <Link to="/datasets/$id" params={{ id: String(j.dataset_id) }} className={v.pill}>
              Open dataset
            </Link>
          )}
          <button
            type="button"
            className={v.pill}
            disabled={cancelling || act.isPending}
            onClick={() => act.mutate({ id: j.id, action: 'cancel' })}
          >
            {cancelling ? 'Cancelling…' : 'Cancel'}
          </button>
        </div>
      </div>
      {ex.steps ? (
        <Steps
          steps={ex.steps}
          step={ex.step}
          cls={{ steps: s.steps, bar: s.stepBar, fill: s.stepFill, done: s.done, now: s.now, muted: v.muted }}
        />
      ) : (
        <div className={v.meter}>
          <span style={{ width: `${(j.progress ?? 0) * 100}%` }} />
        </div>
      )}
      {j.recent_log.length > 0 && (
        <pre className={s.recentLog}>
          {j.recent_log.map(([at, note]) => `${hhmm(at)} ${note}`).join('\n')}
        </pre>
      )}
    </article>
  )
}

function Spark({ data, index, max, cls }: { data: number[][]; index: number; max: number; cls: string }) {
  if (data.length < 2) return null
  const pts = data
    .map((p, i) => `${(i / (data.length - 1)) * 100},${30 - (Math.min(p[index], max) / max) * 28}`)
    .join(' ')
  return <polyline points={pts} className={cls} />
}

function WorkerTile({ w, container }: { w: WorkerT; container: number }) {
  const mb = (n: number | null | undefined) => (n == null ? '—' : `${Math.round(n / 2 ** 20)} MB`)
  const maxRss = Math.max(1, ...w.history.map((p) => p[2]))
  const [open, setOpen] = useState(false)
  const slot = w.id.split('-').pop()
  const helper = w.kind === 'helper'
  const engine = (w.engine_label ?? 'Siril').toLowerCase()
  // everything there is to know, on hover; a click unfolds it in the tile
  const detail = [
    helper ? `Helper ${w.host} (post-processing)` : `Container ${container} (${w.host}) · slot ${slot}`,
    w.job ? `${w.job.name}: ${w.job.target}` : 'Idle',
    w.job?.started_at ? `Started ${hhmm(w.job.started_at)}` : '',
    w.job?.note ?? '',
    w.engine_command ? `${engine} › ${w.engine_command}` : '',
  ]
    .filter(Boolean)
    .join('\n')
  return (
    <article className={`${v.card} ${s.worker}`}>
      <button
        type="button"
        className={s.workerHit}
        title={detail}
        aria-expanded={open}
        onClick={() => setOpen(!open)}
      >
        <span className={s.workerTop}>
          <strong className={v.mono}>{helper ? w.host : `C${container}·${slot}`}</strong>
          <span className={v.muted}>{w.verb}</span>
        </span>
        <span className={`${v.note} ${open ? s.workerJobOpen : s.workerJob}`}>
          {w.job ? w.job.target : 'Idle'}
        </span>
        {w.engine_command && (
          <span className={`${v.mono} ${v.note} ${open ? s.workerJobOpen : s.workerJob}`}>
            {engine} › {w.engine_command}
          </span>
        )}
        {open && w.job?.note && <span className={`${v.note} ${v.muted}`}>{w.job.note}</span>}
      </button>
      <svg
        viewBox="0 0 100 30"
        preserveAspectRatio="none"
        className={s.spark}
        role="img"
        aria-label="CPU and memory, last 15 minutes"
      >
        <Spark
          data={w.history}
          index={1}
          max={Math.max(100, ...w.history.map((p) => p[1]))}
          cls={s.sparkCpu}
        />
        <Spark data={w.history} index={2} max={maxRss} cls={s.sparkRam} />
      </svg>
      <div className={`${v.mono} ${s.workerStats}`}>
        <span>CPU {Math.round(w.cpu_pct ?? 0)}%</span>
        <span>RAM {mb(w.rss_bytes)}</span>
        {(w.engine_rss_bytes ?? 0) > 0 && (
          <span className={v.accent}>
            {w.engine_label ?? 'Siril'} {Math.round(w.engine_cpu_pct ?? 0)}% · {mb(w.engine_rss_bytes)}
          </span>
        )}
      </div>
    </article>
  )
}

/** A link to a job's result that stays in the app (no page reload). */
export function JobLink({ href, children }: { href: string; children: React.ReactNode }) {
  const router = useRouter()
  return (
    <a
      href={href}
      onClick={(e) => {
        if (e.metaKey || e.ctrlKey || e.shiftKey || e.button !== 0) return
        e.preventDefault()
        router.history.push(href)
      }}
    >
      {children}
    </a>
  )
}
