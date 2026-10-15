// Calibration (spec 002 v2 amendment; design v2 D4): which dark and flat each session used, and how good the
// match is, in plain English. Weak flat matches are flagged; sessions waiting for calibration say why.
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link } from '@tanstack/react-router'
import { Fragment, useState } from 'react'
import { api, unwrap } from '../../api/client'
import { optimistic, patchItems } from '../../api/optimistic'
import { toast } from '../../components/Toasts'
import { VerdictIcon } from '../../components/VerdictBadge'
import { Zoomable } from '../../components/CloseLook'
import { Glance } from '../../components/Glance'
import { Spinner } from '../../components/ui'
import c from './calibrationTab.module.css'
import { nightText } from '../format'
import type { Session, Sub } from '../v2/hooks'
import v from '../v2/v2.module.css'
import { useSort } from '../../components/sortable'
import { Collapsible } from '../../components/Collapsible'
import { LoadMore } from '../../components/LoadMore'
import { useProgressive } from '../../components/useProgressive'
import tb from '../library/tables.module.css'

/** A session whose filter was just set: its subs move to that filter's dataset in the background. */
type Move = { filter: string; to: number | null }

/** Newer calibration (002 C11): offered, never applied silently to subs that are already calibrated. */
function Recalibrate({ id }: { id: number }) {
  const qc = useQueryClient()
  const q = useQuery({
    queryKey: ['recalibration', id],
    queryFn: async () => unwrap(await api.GET('/datasets/{id}/recalibration', { params: { path: { id } } })),
  })
  const apply = useMutation({
    mutationFn: async () =>
      unwrap(await api.POST('/datasets/{id}/recalibration', { params: { path: { id } } })),
    scope: { id: `recalibrate-${id}` },
    meta: { failed: "Couldn't re-calibrate" },
    // the offer goes at once; the count of what was queued follows as a note
    ...optimistic(
      qc,
      () => [[['recalibration', id], (o) => o && { ...(o as object), pending: 0 }]],
      () => [
        ['stacks', id],
        ['subs', id],
      ],
    ),
    onSuccess: (r) => toast(`Queued ${r.queued} sub${r.queued === 1 ? '' : 's'} for re-calibration`),
  })
  const n = q.data?.pending ?? 0
  if (!n) return null
  return (
    <output className={v.banner}>
      <VerdictIcon state="stale" size={16} title="" />
      <span>
        <strong>
          Newer calibration for {n} sub{n === 1 ? '' : 's'}
        </strong>{' '}
        in {Object.keys(q.data!.sessions).length} session
        {Object.keys(q.data!.sessions).length === 1 ? '' : 's'}. Re-calibrating re-grades them and marks their
        stacks stale. Manual overrides kept.
      </span>
      <button type="button" className={v.pill} disabled={apply.isPending} onClick={() => apply.mutate()}>
        Re-calibrate
      </button>
    </output>
  )
}

export function CalibrationTab({
  sessions,
  subs,
  datasetId,
}: {
  sessions: Session[]
  subs: Sub[]
  datasetId: number
}) {
  const weak = sessions.filter((x) => x.weak)
  const {
    sorted: sortedSessions,
    th,
    sort,
  } = useSort(sessions, {
    session: (x) => x.night,
    subs: (x) => x.sub_count,
    dark: (x) => x.dark ?? x.dark_note,
    flat: (x) => x.flat ?? x.flat_note,
  })
  const rows = useProgressive(sortedSessions, 60, `${sort?.key}|${sort?.desc}`)
  const waiting = sessions.filter((x) => x.awaiting > 0)
  // Subs leaving a session after a filter change (owner 2026-10-11): the row stays,
  // muted, while its subs move; once a refetch no longer has it, a note says where they went.
  const [moves, setMoves] = useState<Record<string, Move>>({})
  const [editing, setEditing] = useState<string | null>(null)
  const setMove = (night: string, m: Move | null) =>
    setMoves((all) => {
      const next = { ...all }
      if (m) next[night] = m
      else delete next[night]
      return next
    })
  const present = new Set(sessions.map((x) => x.night))
  const moved = Object.entries(moves).filter(([n]) => !present.has(n))
  return (
    <div className={v.page}>
      <Recalibrate id={datasetId} />
      {weak.length > 0 && (
        <output className={v.banner}>
          <VerdictIcon state="down" size={16} title="" />
          <span>
            <strong>
              {weak.length} session{weak.length === 1 ? ' has' : 's have'} a weak flat match.
            </strong>{' '}
            See the flat notes. Grading still ran.
          </span>
        </output>
      )}
      {moved.map(([night, m]) => (
        <output key={night} className={v.banner}>
          <span>
            <strong>{nightText(night)}</strong> moved to {m.filter}.{' '}
            {m.to != null && (
              <Link to="/datasets/$id" params={{ id: String(m.to) }} search={{ tab: 'calibration' }}>
                Open its dataset
              </Link>
            )}
          </span>
          <button type="button" className={v.pill} onClick={() => setMove(night, null)}>
            Dismiss
          </button>
        </output>
      ))}
      {waiting.length > 0 && (
        <output className={v.banner}>
          <VerdictIcon state="await" size={16} title="" />
          <span>
            <strong>{waiting.reduce((n, x) => n + x.awaiting, 0)} subs awaiting calibration.</strong>{' '}
            {subs.find((x) => x.awaiting_reason)?.awaiting_reason}{' '}
            <Link to="/calibration">Calibration library</Link>
          </span>
        </output>
      )}
      <section className={`${v.card} ${tb.flush}`}>
        <Collapsible id="calibration-sessions" title="Sessions" meta={sessions.length}>
          <div className={tb.pane}>
            <table className={`${v.table} ${tb.table} cards`}>
              <thead>
                <tr>
                  {th('session', 'Session', tb.nowrap)}
                  {th('subs', 'Subs', tb.num)}
                  {th('dark', 'Dark or bias')}
                  {th('flat', 'Flat')}
                  <th className={tb.act}>
                    <span className="visually-hidden">Change</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {rows.visible.map((x) => {
                  const move = moves[x.night]
                  return (
                    <Fragment key={x.night}>
                      <tr className={move ? tb.muted : undefined} aria-busy={!!move}>
                        <td className={tb.nowrap}>
                          <strong>{nightText(x.night)}</strong>
                        </td>
                        <td className={`${v.mono} ${tb.num}`} data-label="Subs">
                          {x.sub_count}
                        </td>
                        <td data-label="Dark or bias">
                          {x.dark ? (
                            <>
                              <div className={v.mono}>{x.dark}</div>
                              <div className={`${v.note} ${v.ok}`}>{x.dark_note}</div>
                            </>
                          ) : x.dark_note ? (
                            <span className={v.muted}>{x.dark_note}</span>
                          ) : (
                            <span className={v.warn}>No dark yet</span>
                          )}
                        </td>
                        <td data-label="Flat">
                          {x.flat ? (
                            <>
                              {x.flat_sha && (
                                <FlatThumb sha={x.flat_sha} thumb={x.flat_thumb ?? null} label={x.flat} />
                              )}
                              <div className={v.mono}>{x.flat}</div>
                              <div className={`${v.note} ${x.weak ? v.warn : v.ok}`}>{x.flat_note}</div>
                            </>
                          ) : x.flat_note ? (
                            <span className={v.muted}>{x.flat_note}</span>
                          ) : (
                            <span className={v.warn}>No flat yet</span>
                          )}
                        </td>
                        <td className={tb.act}>
                          {move ? (
                            <span className={v.muted}>
                              Moving to {move.filter}…{' '}
                              {move.to != null && (
                                <Link
                                  to="/datasets/$id"
                                  params={{ id: String(move.to) }}
                                  search={{ tab: 'calibration' }}
                                >
                                  Open its dataset
                                </Link>
                              )}
                            </span>
                          ) : (
                            <div className={`${v.actions} ${c.rowActions}`}>
                              <button
                                type="button"
                                className={v.pill}
                                aria-expanded={editing === x.night}
                                onClick={() => setEditing(editing === x.night ? null : x.night)}
                              >
                                Change
                              </button>
                              <SessionFilter
                                datasetId={datasetId}
                                night={x.night}
                                onMove={(m) => setMove(x.night, m)}
                              />
                            </div>
                          )}
                        </td>
                      </tr>
                      {editing === x.night && (
                        <tr className={c.panelRow}>
                          <td colSpan={5}>
                            <ChangePanel
                              datasetId={datasetId}
                              night={x.night}
                              onClose={() => setEditing(null)}
                            />
                          </td>
                        </tr>
                      )}
                    </Fragment>
                  )
                })}
              </tbody>
            </table>
            <LoadMore hasMore={rows.hasMore} loading={false} onMore={rows.more} />
          </div>
        </Collapsible>
      </section>
      <p className={`${v.muted} ${v.note}`}>
        Darks match exposure, gain, offset, binning, size and temperature (±2 °C), or bias for "flats and
        bias" rigs. Flats match filter, camera, telescope, binning and size: latest on or before the session.
      </p>
    </div>
  )
}

/** A flat you can see (owner 2026-10-11: confirm it's a Duo NB flat): thumbnail, click for 100%. */
function FlatThumb({ sha, thumb, label }: { sha: string; thumb: string | null; label: string }) {
  return (
    <div className={c.flatImg}>
      <Zoomable target={{ kind: 'sub', sha }} name={label}>
        {thumb ? <img src={thumb} alt={label} loading="lazy" /> : <span className={v.muted}>View</span>}
      </Zoomable>
    </div>
  )
}

/** Change (002-DR-07; owner 2026-10-12): other masters for this session only, in a full-width row under it. Flats of the session's filter
 * come first, nearest night first; other filters are one click away for a session whose filter is mislabelled. */
// the flat table's columns, set on header and body cells alike (its body scrolls on its own)
const COLS = ['44px', '27%', '8%', '15%', '14%', '8%', '13%', 'auto']

function ChangePanel({
  datasetId,
  night,
  onClose,
}: {
  datasetId: number
  night: string
  onClose: () => void
}) {
  const qc = useQueryClient()
  const [pick, setPick] = useState<{ dark?: string; flat?: string }>({})
  const [others, setOthers] = useState(false)
  const flatSet = pick.flat?.startsWith('set:') ? Number(pick.flat.slice(4)) : null
  const q = useQuery({
    queryKey: ['session-choices', datasetId, night],
    queryFn: async () =>
      unwrap(
        await api.GET('/datasets/{id}/sessions/{night}/calibration', {
          params: { path: { id: datasetId, night } },
        }),
      ),
  })
  // shown in the session row at once, labelled as yours; the dialog closes on click
  type Choice = {
    dark?: string
    flat?: string
    flatSet: number | null
    darkLabel?: string
    flatLabel?: string
    flatSha?: string | null
    flatThumb?: string | null
  }
  const apply = useMutation({
    mutationFn: async ({ dark, flat, flatSet: set }: Choice) =>
      unwrap(
        await api.POST('/datasets/{id}/sessions/{night}/calibration', {
          params: { path: { id: datasetId, night } },
          body: {
            dark: dark ?? null,
            flat: set == null ? (flat ?? null) : null,
            flat_set: set,
            automatic: false,
          },
        }),
      ),
    scope: { id: `session-${datasetId}-${night}` },
    meta: { failed: "Couldn't change the calibration" },
    ...optimistic(
      qc,
      (ch: Choice) => [
        [
          ['sessions', datasetId],
          (o) =>
            patchItems<Session>(
              o,
              (x) => x.night === night,
              (x) => ({
                ...x,
                ...(ch.darkLabel ? { dark: ch.darkLabel, dark_note: 'Chosen by you' } : {}),
                ...(ch.flatLabel
                  ? {
                      flat: ch.flatLabel,
                      flat_note: 'Chosen by you',
                      weak: false,
                      flat_sha: ch.flatSha ?? null,
                      flat_thumb: ch.flatThumb ?? null,
                    }
                  : {}),
              }),
            ),
        ],
      ],
      () => [
        ['stacks', datasetId],
        ['subs', datasetId],
      ],
    ),
  })
  const automatic = useMutation({
    mutationFn: async () =>
      unwrap(
        await api.POST('/datasets/{id}/sessions/{night}/calibration', {
          params: { path: { id: datasetId, night } },
          body: { automatic: true },
        }),
      ),
    onSuccess: (r) =>
      toast(
        r.pending
          ? `Back to automatic: ${r.pending} sub${r.pending === 1 ? '' : 's'} wait for a matching dark or flat`
          : `Back to automatic: ${r.queued} sub${r.queued === 1 ? '' : 's'} calibrating`,
      ),
    onSettled: () => void qc.invalidateQueries(),
    meta: { failed: "Couldn't go back to automatic" },
  })
  type Row = {
    key: string
    sha: string | null
    thumb: string | null
    label: string
    filter: string
    night: string | null
    days: number | null
    frames: number | null
    telescope: string
    state: string
    same: boolean
    setId?: number // a flat set opens on its own page
  }
  const flats: Row[] = [
    ...(q.data?.flat_sets ?? []).map((f) => ({
      key: `set:${f.set_id}`,
      sha: f.sha ?? null,
      thumb: f.thumb ?? null,
      label: f.label,
      filter: f.filter ?? '',
      night: f.night ?? null,
      days: f.days ?? null,
      frames: f.frames ?? null,
      telescope: f.telescope ?? '',
      state: f.built ? 'Built' : 'To build',
      same: f.same_filter ?? true,
      setId: f.set_id,
    })),
    ...(q.data?.flats ?? []).map((m) => ({
      key: m.sha256,
      sha: m.sha256 as string | null,
      thumb: m.thumb ?? null,
      label: m.label,
      filter: m.filter ?? '',
      night: m.night ?? null,
      days: m.days ?? null,
      frames: m.frames ?? null,
      telescope: m.telescope ?? '',
      state: 'Library master',
      same: m.same_filter ?? true,
    })),
  ].sort((x, y) => Math.abs(x.days ?? 9999) - Math.abs(y.days ?? 9999))
  const mine = flats.filter((f) => f.same)
  const other = flats.filter((f) => !f.same)
  const shown = others ? [...mine, ...other] : mine
  const fitting = (q.data?.darks ?? []).filter((m) => !(m.mismatch ?? []).length)
  const misfits = (q.data?.darks ?? []).filter((m) => (m.mismatch ?? []).length)
  const pickedMisfit = misfits.find((m) => m.sha256 === pick.dark)
  const use = () => {
    if (pick.dark === 'auto') {
      automatic.mutate()
      onClose()
      return
    }
    const flat = flats.find((f) => f.key === pick.flat)
    apply.mutate({
      ...pick,
      flatSet,
      darkLabel: q.data?.darks.find((m) => m.sha256 === pick.dark)?.label,
      flatLabel: flat?.label,
      flatSha: flat?.sha,
      flatThumb: flat?.thumb,
    })
    onClose()
  }
  const when = (d: number | null) =>
    d == null
      ? ''
      : d === 0
        ? 'same night'
        : `${Math.abs(d)} day${Math.abs(d) === 1 ? '' : 's'} ${d < 0 ? 'before' : 'after'}`
  return (
    <div className={c.panel}>
      <div className={v.actions}>
        <label className={c.darkPick}>
          <span className={v.muted}>Dark or bias</span>
          <select
            className={v.select}
            value={pick.dark ?? ''}
            onChange={(e) => setPick({ ...pick, dark: e.target.value || undefined })}
          >
            <option value="">Keep the current one</option>
            <option value="auto">Automatic: let SubStation choose</option>
            {/* what fits first; the rest say how they differ, so a mismatch is never picked unawares (002-DR-26) */}
            <optgroup label="Match these subs">
              {fitting.map((m) => (
                <option key={m.sha256} value={m.sha256}>
                  {m.label}
                  {m.note ? ` · ${m.note}` : ''}
                </option>
              ))}
            </optgroup>
            {misfits.length > 0 && (
              <optgroup label="Don't match these subs">
                {misfits.map((m) => (
                  <option key={m.sha256} value={m.sha256}>
                    ✗ {m.label} · {(m.mismatch ?? []).join('; ')}
                  </option>
                ))}
              </optgroup>
            )}
          </select>
        </label>
      </div>
      {fitting.length === 0 && q.data && (
        <p className={v.warn}>
          No master dark or bias matches these subs. A dark that doesn't match leaves the wrong bias level and
          dark current in every sub; shoot one at their settings, or leave the session waiting.
        </p>
      )}
      {pickedMisfit && (
        <p className={v.warn}>
          That one doesn't match these subs: {(pickedMisfit.mismatch ?? []).join('; ')}. It will calibrate
          them, but not well.
        </p>
      )}
      {q.isPending && <Spinner label="Loading flats" />}
      {q.data && (
        <>
          <table className={`${v.table} ${tb.table} ${c.flatTable} cards`}>
            <thead>
              <tr>
                <th style={{ width: COLS[0] }} className={tb.act}>
                  <span className="visually-hidden">Use</span>
                </th>
                <th style={{ width: COLS[1] }}>Flat</th>
                <th style={{ width: COLS[2] }}>Filter</th>
                <th style={{ width: COLS[3] }} className={tb.nowrap}>
                  Night
                </th>
                <th style={{ width: COLS[4] }} className={tb.nowrap}>
                  From this session
                </th>
                <th style={{ width: COLS[5] }} className={tb.num}>
                  Frames
                </th>
                <th style={{ width: COLS[6] }}>Telescope</th>
                <th style={{ width: COLS[7] }}>State</th>
              </tr>
            </thead>
            <tbody>
              {shown.map((f) => {
                const on = pick.flat === f.key
                const choose = () => setPick({ ...pick, flat: on ? undefined : f.key })
                return (
                  <tr
                    key={f.key}
                    className={`${c.flatRow} ${on ? c.flatOn : ''} ${f.same ? '' : c.otherFilter}`}
                    onClick={choose}
                  >
                    <td style={{ width: COLS[0] }} className={tb.act} data-label="Use">
                      <input
                        type="radio"
                        name={`flat-${night}`}
                        checked={on}
                        onChange={choose}
                        aria-label={`Use ${f.label}`}
                      />
                    </td>
                    <td style={{ width: COLS[1] }}>
                      {(() => {
                        const name = f.setId ? (
                          <Link
                            to="/calibration/sets/$id"
                            params={{ id: String(f.setId) }}
                            className={v.mono}
                            onClick={(e) => e.stopPropagation()}
                            title="Open this flat set"
                          >
                            {f.label}
                          </Link>
                        ) : (
                          <span className={v.mono}>{f.label}</span>
                        )
                        return f.sha ? (
                          <Glance sha={f.sha} label={f.label}>
                            {name}
                          </Glance>
                        ) : (
                          name
                        )
                      })()}
                    </td>
                    <td
                      style={{ width: COLS[2] }}
                      className={f.same ? undefined : v.warn}
                      data-label="Filter"
                    >
                      {f.filter || '—'}
                    </td>
                    <td style={{ width: COLS[3] }} className={`${tb.nowrap} ${v.mono}`} data-label="Night">
                      {f.night ? nightText(f.night) : '—'}
                    </td>
                    <td style={{ width: COLS[4] }} className={tb.nowrap} data-label="From this session">
                      {when(f.days)}
                    </td>
                    <td style={{ width: COLS[5] }} className={`${v.mono} ${tb.num}`} data-label="Frames">
                      {f.frames ?? '—'}
                    </td>
                    <td style={{ width: COLS[6] }} className={v.muted} data-label="Telescope">
                      {f.telescope || '—'}
                    </td>
                    <td style={{ width: COLS[7] }} className={v.muted} data-label="State">
                      {f.state}
                    </td>
                  </tr>
                )
              })}
              {!shown.length && (
                <tr>
                  <td colSpan={8} className={v.muted}>
                    No flats for this filter yet.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
          {other.length > 0 && (
            <button type="button" className={`${v.pill} ${c.otherToggle}`} onClick={() => setOthers(!others)}>
              {others
                ? 'Hide other filters'
                : `Show other filters (${other.length}): only if this session's filter is wrong`}
            </button>
          )}
        </>
      )}
      <div className={v.actions}>
        <button type="button" className={v.pill} disabled={!(pick.dark || pick.flat)} onClick={use}>
          {pick.dark === 'auto' ? 'Go back to automatic' : 'Use and re-calibrate'}
        </button>
        <button type="button" className={v.pill} onClick={onClose}>
          Cancel
        </button>
      </div>
    </div>
  )
}

/** Filter (owner 2026-10-10): say which filter the whole session used, e.g. a Duo NB the headers call OSC.
 * The subs move to that filter's dataset, get its flats and are measured again. */
function SessionFilter({
  datasetId,
  night,
  onMove,
}: {
  datasetId: number
  night: string
  onMove: (m: Move | null) => void
}) {
  const qc = useQueryClient()
  const [open, setOpen] = useState(false)
  const [value, setValue] = useState('')
  const q = useQuery({
    queryKey: ['session-choices', datasetId, night],
    enabled: open,
    queryFn: async () =>
      unwrap(
        await api.GET('/datasets/{id}/sessions/{night}/calibration', {
          params: { path: { id: datasetId, night } },
        }),
      ),
  })
  const apply = useMutation({
    mutationFn: async (filter: string) =>
      unwrap(
        await api.POST('/datasets/{id}/sessions/{night}/filter', {
          params: { path: { id: datasetId, night } },
          body: { filter },
        }),
      ),
    scope: { id: `session-${datasetId}-${night}` },
    meta: { failed: "Couldn't set the filter" },
    // the row says it's moving at once; the link to the filter's dataset follows from the reply. Mutation
    // options, not mutate() callbacks, so they still land if this row has gone by then.
    onMutate: (filter) => onMove({ filter, to: null }),
    onSuccess: (r, filter) => {
      void qc.invalidateQueries()
      onMove(r.dataset_id && r.dataset_id !== datasetId ? { filter, to: r.dataset_id } : null)
    },
    onError: () => onMove(null),
  })
  const listId = `filters-${datasetId}-${night}`
  if (!open)
    return (
      <button
        type="button"
        className={v.pill}
        onClick={() => setOpen(true)}
        title="Set filter for this session"
      >
        {/* the session has no filter column; the chosen one shows here until its subs have moved */}
        {apply.isPending ? `Filter: ${apply.variables}…` : 'Filter…'}
      </button>
    )
  return (
    <div className={v.actions}>
      <input
        className={v.select}
        style={{ maxWidth: 160 }}
        list={listId}
        value={value}
        placeholder="e.g. Duo NB"
        aria-label="Session filter"
        onChange={(e) => setValue(e.target.value)}
      />
      <datalist id={listId}>
        {q.data?.filters?.map((f) => (
          <option key={f} value={f}>
            {f}
          </option>
        ))}
      </datalist>
      <button
        type="button"
        className={v.pill}
        disabled={!value.trim()}
        onClick={() => {
          apply.mutate(value.trim())
          setOpen(false)
        }}
      >
        Set for this session
      </button>
      <button type="button" className={v.pill} onClick={() => setOpen(false)}>
        Cancel
      </button>
    </div>
  )
}
