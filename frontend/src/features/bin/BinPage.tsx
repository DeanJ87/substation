// The bin (spec 011, 011-DR-07): everything binned, why, and when it goes for good; restore one or many. How long
// things wait and which libraries may be deleted from are settings (Settings → Library → Bin).
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link } from '@tanstack/react-router'
import { useMemo, useState } from 'react'
import { api, unwrap } from '../../api/client'
import { toast } from '../../components/Toasts'
import { Button, ConfirmButton, EmptyState, ErrorState, PageLoading } from '../../components/ui'
import { bytes } from '../format'
import v from '../v2/v2.module.css'
import s from './bin.module.css'

const PAGE = 200
const day = (iso: string | null | undefined) =>
  iso ? new Date(iso).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' }) : ''
const TYPE: Record<string, string> = {
  light: 'Light',
  dark: 'Dark',
  flat: 'Flat',
  bias: 'Bias',
  dark_flat: 'Dark flat',
  master_dark: 'Master dark',
  master_flat: 'Master flat',
  master_bias: 'Master bias',
}

export function BinPage() {
  const qc = useQueryClient()
  const [limit, setLimit] = useState(PAGE)
  const [picked, setPicked] = useState<Set<string>>(new Set())
  const [reason, setReason] = useState('')
  const q = useQuery({
    queryKey: ['bin', limit],
    queryFn: async () => unwrap(await api.GET('/bin', { params: { query: { offset: 0, limit } } })),
  })
  const restore = useMutation({
    mutationFn: async (sha256s: string[]) =>
      unwrap(await api.POST('/bin/restore', { body: { sha256s, reason: '' } })),
    onSuccess: (r) => {
      toast(
        r.not_restored
          ? `${r.restored} restored; ${r.not_restored} couldn't be (something else is in their old place).`
          : `${r.restored} restored.`,
      )
      setPicked(new Set())
    },
    onSettled: () => void qc.invalidateQueries(),
    meta: { failed: "Couldn't restore" },
  })
  const tidy = useMutation({
    mutationFn: async () => unwrap(await api.POST('/bin/tidy')),
    onSuccess: () => toast('Tidying the bin.'),
    onSettled: () => void qc.invalidateQueries({ queryKey: ['bin'] }),
    meta: { failed: "Couldn't start the tidy" },
  })
  const d = q.data
  const reasons = useMemo(() => {
    const m = new Map<string, number>()
    for (const r of d?.rows ?? [])
      m.set(r.reason || 'No reason given', (m.get(r.reason || 'No reason given') ?? 0) + 1)
    return [...m.entries()].sort((a, b) => b[1] - a[1])
  }, [d])
  const rows = (d?.rows ?? []).filter((r) => !reason || (r.reason || 'No reason given') === reason)
  if (q.isError)
    return (
      <ErrorState title="Couldn't load the bin" onRetry={() => q.refetch()}>
        {q.error.message}
      </ErrorState>
    )
  if (!d) return <PageLoading />
  const space = bytes(d.bytes_in_quarantine)
  const allPicked = rows.length > 0 && rows.every((r) => picked.has(r.sha256))
  const toggle = (sha: string) => {
    const next = new Set(picked)
    if (next.has(sha)) next.delete(sha)
    else next.add(sha)
    setPicked(next)
  }
  return (
    <div className={v.page}>
      <header className={v.head}>
        <div>
          <h1>Bin</h1>
          <div className={v.sub}>
            Binned files leave SubStation at once. Where SubStation may delete, they wait in a hidden
            quarantine folder and are deleted after {d.purge_after_days} days; elsewhere they're only hidden.
            Their records stay, so your history still counts them.
          </div>
        </div>
        <div className={v.actions}>
          <Link to="/settings" hash="bin" className={v.pill}>
            Bin settings
          </Link>
        </div>
      </header>

      <div className={v.readouts}>
        <div className={v.readout}>
          <div className={v.readoutLabel}>In the bin</div>
          <div className={v.readoutValue}>{d.total.toLocaleString('en-GB')}</div>
          <div className={v.readoutDetail}>files</div>
        </div>
        <div className={v.readout}>
          <div className={v.readoutLabel}>In quarantine</div>
          <div className={v.readoutValue}>
            {d.bytes_in_quarantine ? (
              <>
                {space.value} <span className={s.unit}>{space.unit}</span>
              </>
            ) : (
              'None'
            )}
          </div>
          <div className={v.readoutDetail}>{d.moved.toLocaleString('en-GB')} files waiting to be deleted</div>
        </div>
        <div className={v.readout}>
          <div className={v.readoutLabel}>Only hidden</div>
          <div className={v.readoutValue}>{d.hidden.toLocaleString('en-GB')}</div>
          <div className={v.readoutDetail}>in libraries SubStation may not delete from</div>
        </div>
        <div className={v.readout}>
          <div className={v.readoutLabel}>Deleted so far</div>
          <div className={v.readoutValue}>{d.deleted.toLocaleString('en-GB')}</div>
          <div className={v.readoutDetail}>records kept for history</div>
        </div>
      </div>

      <section className={`${v.card} ${s.tidy}`}>
        <div>
          <strong>Daily tidy</strong>
          <p className={v.muted}>
            Once a day SubStation bins subs that have been rejected for more than {d.auto_bin_rejected_days}{' '}
            days
            {d.auto_bin_rejected_days ? '' : ' (switched off)'}, unless you've kept them, and deletes
            quarantined files whose date has passed. "Tidy now" runs it straight away.
          </p>
        </div>
        <Button disabled={tidy.isPending} onClick={() => tidy.mutate()}>
          Tidy now
        </Button>
      </section>

      {d.total === 0 ? (
        <EmptyState title="The bin is empty">
          Files you bin, and rejected subs once they've waited, show here.
        </EmptyState>
      ) : (
        <section className={v.card}>
          <div className={s.bar}>
            <div className={v.pills} role="group" aria-label="Why they were binned">
              <button type="button" className={v.pill} aria-pressed={!reason} onClick={() => setReason('')}>
                All <span className={v.mono}>{(d.rows ?? []).length}</span>
              </button>
              {reasons.map(([r, n]) => (
                <button
                  key={r}
                  type="button"
                  className={v.pill}
                  aria-pressed={reason === r}
                  onClick={() => setReason(r)}
                  title={r}
                >
                  {r.length > 48 ? `${r.slice(0, 46)}…` : r} <span className={v.mono}>{n}</span>
                </button>
              ))}
            </div>
            {picked.size ? (
              <ConfirmButton
                question={
                  <>
                    Restore {picked.size} file{picked.size === 1 ? '' : 's'} to where they were?
                  </>
                }
                confirm="Restore"
                onConfirm={() => restore.mutate([...picked])}
              >
                Restore {picked.size}
              </ConfirmButton>
            ) : (
              <Button disabled>Restore</Button>
            )}
          </div>
          <div className={s.pane}>
            <table className={`${s.table} cards`}>
              <thead>
                <tr>
                  <th className={s.check}>
                    <input
                      type="checkbox"
                      aria-label="Select all shown"
                      checked={allPicked}
                      onChange={() => setPicked(allPicked ? new Set() : new Set(rows.map((r) => r.sha256)))}
                    />
                  </th>
                  <th>
                    <span className={s.hidden}>Preview</span>
                  </th>
                  <th>File</th>
                  <th>Why</th>
                  <th>Binned</th>
                  <th>Goes</th>
                  <th className={s.num}>Size</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => {
                  const size = bytes(r.size_bytes)
                  return (
                    <tr key={r.sha256} className={picked.has(r.sha256) ? s.picked : ''}>
                      <td className={s.check} data-label="">
                        <input
                          type="checkbox"
                          aria-label={`Select ${r.name}`}
                          checked={picked.has(r.sha256)}
                          onChange={() => toggle(r.sha256)}
                        />
                      </td>
                      <td className={s.thumbCell} data-label="">
                        <img
                          className={s.thumb}
                          src={`/api/v1/frames/${r.sha256}/glance`}
                          alt={`Preview of ${r.name}`}
                          loading="lazy"
                        />
                      </td>
                      <td>
                        <div className={`${v.mono} ${s.name}`} title={r.name}>
                          {r.name}
                        </div>
                        <div className={v.muted}>
                          {TYPE[r.frame_type] ?? r.frame_type}
                          {r.target ? ` · ${r.target}` : ''}
                        </div>
                      </td>
                      <td className={s.why} data-label="Why" data-wide>
                        {r.reason || 'No reason given'}
                        {r.by ? <div className={v.muted}>by {r.by}</div> : null}
                      </td>
                      <td className={s.nowrap} data-label="Binned">
                        {day(r.binned_at)}
                      </td>
                      <td className={s.nowrap} data-label="Goes">
                        {r.purge_after ? `deleted ${day(r.purge_after)}` : 'hidden only'}
                      </td>
                      <td className={`${s.num} ${v.mono}`} data-label="Size">
                        {size.value} {size.unit}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
          {d.total > (d.rows ?? []).length && (
            <div className={s.more}>
              <Button onClick={() => setLimit(limit + PAGE)}>
                Show more ({(d.total - (d.rows ?? []).length).toLocaleString('en-GB')} not shown)
              </Button>
            </div>
          )}
        </section>
      )}
    </div>
  )
}
