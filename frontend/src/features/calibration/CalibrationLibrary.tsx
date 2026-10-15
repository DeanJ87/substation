// Calibration library (T097): raw calibration sets by night, and imported masters with the values calibration
// matching needs (and where each came from). Building masters is spec 002.
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link, useNavigate } from '@tanstack/react-router'
import { useMemo, useState } from 'react'
import { api, unwrap } from '../../api/client'
import { optimistic, patchItems } from '../../api/optimistic'
import type { components } from '../../api/schema'
import { Button, ConfirmButton, EmptyState, ErrorState, Spinner } from '../../components/ui'
import { VerdictBadge, type VerdictState } from '../../components/VerdictBadge'
import { useCalibrationActions } from '../v2/hooks'
import { useCatalogueLiveUpdates } from '../datasets/queries'
import { FrameDetail } from '../frames/FrameDetail'
import { Zoomable } from '../../components/CloseLook'
import { agoText, nightText, temp } from '../format'
import ui from '../../components/ui.module.css'
import v from '../v2/v2.module.css'
import s from './calibration.module.css'
import { useSort } from '../../components/sortable'
import { Collapsible } from '../../components/Collapsible'
import { LoadMore } from '../../components/LoadMore'
import { useProgressive } from '../../components/useProgressive'
import { ScopeBar } from '../scope/ScopeBar'
import { scopeParams, scopeQuery, type Scope } from '../scope/scope'
import { useScope } from '../scope/useScope'

type CalSet = components['schemas']['CalibrationSetOut']
type Master = components['schemas']['MasterOut']
type Blocked = components['schemas']['BlockingOut']

/** The rig a master belongs to, as headers name it: camera, and telescope when recorded. */
const rigOf = (m: Master) => [m.camera, m.telescope].filter(Boolean).join(' · ') || 'Unknown'

const TYPE: Record<string, string> = {
  flat: 'Flats',
  dark: 'Darks',
  dark_flat: 'Dark flats',
  bias: 'Bias',
  master_dark: 'Master dark',
  master_flat: 'Master flat',
  master_bias: 'Master bias',
  master_dark_flat: 'Master dark flat',
}

const BUILT: Record<string, [VerdictState, string]> = {
  queued: ['integ', 'Queued'],
  running: ['integ', 'Building'],
  done: ['accept', 'Master built'],
  failed: ['reject', 'Build failed'],
  blocked: ['await', 'Blocked'],
}

const hhmm = (iso: string) =>
  new Date(iso).toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit', timeZone: 'UTC' })

export function CalibrationLibrary() {
  useCatalogueLiveUpdates()
  // the same filters as the Library, by the same names, in the address (spec 018); the server narrows the lists
  const [scope, setScope] = useScope()
  const query = scopeQuery(scope)
  const sets = useQuery({
    queryKey: ['calibration-sets', query],
    queryFn: async () => unwrap(await api.GET('/calibration-sets', { params: { query } })),
    placeholderData: (prev) => prev,
  })
  const masters = useQuery({
    queryKey: ['masters', query],
    queryFn: async () => unwrap(await api.GET('/masters', { params: { query } })),
    placeholderData: (prev) => prev,
  })
  const [selected, setSelected] = useState<string | null>(null)
  const filters = useMemo(
    () =>
      [
        ...new Set(
          [...(masters.data ?? []), ...(sets.data ?? [])]
            .map((m) => m.filter)
            .filter((x): x is string => !!x),
        ),
      ].sort(),
    [masters.data, sets.data],
  )
  const rigs = useMemo(() => [...new Set((masters.data ?? []).map(rigOf))].sort(), [masters.data])
  const act = useCalibrationActions()
  const navigate = useNavigate()
  const openSet = (id: number) => void navigate({ to: '/calibration/sets/$id', params: { id: String(id) } })

  // 002-DR-01: the folders calibration frames come from, when they were last scanned, and a Rescan
  const libs = useQuery({
    queryKey: ['libraries'],
    queryFn: async () => unwrap(await api.GET('/libraries')),
  })
  const folders = (libs.data ?? []).filter((l) => l.enabled)
  const lastScan = folders
    .map((l) => l.last_full_sweep_at)
    .filter((x): x is string => !!x)
    .sort()
    .at(-1)
  const rescan = useMutation({
    mutationFn: async () => {
      for (const l of folders)
        unwrap(await api.POST('/libraries/{id}/rescan', { params: { path: { id: l.id } } }))
    },
    meta: { failed: "Couldn't start the rescan" },
  })
  const byNight = useMemo(() => {
    const m = new Map<string, CalSet[]>()
    for (const cs of sets.data ?? []) {
      const k = cs.night ?? 'unknown'
      m.set(k, [...(m.get(k) ?? []), cs])
    }
    return [...m.entries()]
  }, [sets.data])
  // a new search or filter starts each long list again from the top
  const filterKey = scopeParams(scope)
  const nights = useProgressive(byNight, 8, filterKey)
  const setCount = byNight.reduce((n, [, l]) => n + l.length, 0)

  if (sets.isError || masters.isError)
    return (
      <ErrorState
        title="Couldn't load the calibration library"
        onRetry={() => (sets.refetch(), masters.refetch())}
      >
        {(sets.error ?? masters.error)?.message}
      </ErrorState>
    )

  return (
    <div className={s.page}>
      <header className={s.head}>
        <div>
          <h1>Calibration</h1>
          <p className="muted">
            {(masters.data ?? []).length} masters across {rigs.length} rig{rigs.length === 1 ? '' : 's'} ·{' '}
            {(sets.data ?? []).length} raw sets from {folders.length} folder{folders.length === 1 ? '' : 's'}{' '}
            · last scan {agoText(lastScan)}
          </p>
        </div>
        <div className={s.headButtons}>
          <Link to="/calibration/to-shoot" search={query} className={v.pill}>
            What to shoot
          </Link>
          <Button onClick={() => rescan.mutate()} disabled={rescan.isPending || !folders.length}>
            {rescan.isPending || rescan.isSuccess ? 'Rescanning…' : 'Rescan'}
          </Button>
          <Button
            variant="primary"
            onClick={() => act.buildMissing.mutate()}
            disabled={act.buildMissing.isPending}
          >
            {act.buildMissing.isPending ? 'Queuing…' : 'Build missing masters'}
          </Button>
        </div>
      </header>
      <ScopeBar
        scope={scope}
        onChange={setScope}
        filters={filters}
        search="Search type, filter, camera, month"
      />
      {act.buildMissing.data && (
        <p className="muted">
          {act.buildMissing.data.queued
            ? `${act.buildMissing.data.queued} queued.`
            : 'All sets have masters.'}
        </p>
      )}

      <Blocking scope={scope} />
      <NewerCalibration scope={scope} />

      <MastersTable
        masters={masters.data ?? []}
        filterKey={filterKey}
        loading={masters.isPending}
        onOpen={setSelected}
      />

      <Collapsible
        id="calibration-raw-sets"
        title="Raw sets"
        meta={
          sets.isSuccess &&
          `${setCount.toLocaleString('en-GB')} set${setCount === 1 ? '' : 's'} · ${byNight.length} night${byNight.length === 1 ? '' : 's'}`
        }
      >
        {sets.isSuccess && byNight.length === 0 && (
          <EmptyState title="No calibration frames yet">
            Flats, darks and bias appear here once catalogued.
          </EmptyState>
        )}
        <div className={`${s.pane} ${s.nights}`}>
          {nights.visible.map(([night, list], i) => (
            <NightSets key={night} night={night} list={list} open={i < 3} onOpen={openSet} />
          ))}
          <LoadMore hasMore={nights.hasMore} loading={false} onMore={nights.more} />
        </div>
      </Collapsible>

      <FrameDetail sha256={selected} onClose={() => setSelected(null)} />
    </div>
  )
}

/** One night's raw sets; the newest few nights start open, the rest folded (remembered once you choose). */
function NightSets({
  night,
  list,
  open,
  onOpen,
}: {
  night: string
  list: CalSet[]
  open: boolean
  onOpen: (id: number) => void
}) {
  return (
    <Collapsible
      id={`calibration-night-${night}`}
      title={night === 'unknown' ? 'Night unknown' : nightText(night)}
      meta={`${list.length} set${list.length === 1 ? '' : 's'}`}
      defaultOpen={open}
    >
      <div className={s.tableWrap}>
        <table className={ui.table}>
          <thead>
            <tr>
              <th>Type</th>
              <th>Filter</th>
              <th className={s.num}>Exposure</th>
              <th className={s.num}>Frames</th>
              <th className={s.num}>Session (UTC)</th>
              <th className={s.num}>Gain / offset</th>
              <th className={s.num}>Bin</th>
              <th className={s.num}>Set temp</th>
              <th>Master</th>
            </tr>
          </thead>
          <tbody>
            {list.map((cs) => (
              <tr
                key={cs.id}
                className={s.clickable}
                tabIndex={0}
                onClick={() => onOpen(cs.id)}
                onKeyDown={(e) => e.key === 'Enter' && onOpen(cs.id)}
              >
                <td className={s.nowrap}>
                  <Link
                    to="/calibration/sets/$id"
                    params={{ id: String(cs.id) }}
                    onClick={(e) => e.stopPropagation()}
                  >
                    {TYPE[cs.type] ?? cs.type}
                  </Link>
                </td>
                <td>
                  {cs.filter ??
                    Object.entries(cs.filter_blocks)
                      .map(([f, n]) => `${f} ×${n}`)
                      .join(', ')}
                </td>
                <td className={`mono ${s.num}`}>{cs.exptime_s} s</td>
                <td className={`mono ${s.num}`}>{cs.frame_count}</td>
                <td className={`mono ${s.num}`}>
                  {hhmm(cs.session_start_utc)}–{hhmm(cs.session_end_utc)}
                </td>
                <td className={`mono ${s.num}`}>
                  {cs.gain ?? '—'} / {cs.offset ?? '—'}
                </td>
                <td className={`mono ${s.num}`}>{cs.binning}</td>
                <td className={s.num}>{temp(cs.set_temp_c)}</td>
                <td className={s.nowrap}>
                  {cs.built_state && BUILT[cs.built_state] ? (
                    <VerdictBadge state={BUILT[cs.built_state][0]} label={BUILT[cs.built_state][1]} />
                  ) : (
                    <span className="muted">—</span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Collapsible>
  )
}

/** What is stopping grading (002-DR-02), above everything else; within the page's scope (spec 018). */
function Blocking({ scope }: { scope: Scope }) {
  const query = scopeQuery(scope)
  const q = useQuery({
    queryKey: ['calibration-blocking', query],
    queryFn: async () => unwrap(await api.GET('/calibration/blocking', { params: { query } })),
  })
  const rows: Blocked[] = q.data ?? []
  const { visible, hasMore, more } = useProgressive(rows, 30)
  if (!rows.length) return null
  const subs = rows.reduce((n, b) => n + b.subs, 0)
  return (
    <Collapsible
      id="calibration-blocking"
      title="Waiting for calibration"
      meta={`${subs.toLocaleString('en-GB')} subs · ${rows.length} session${rows.length === 1 ? '' : 's'}`}
      className={s.blocking}
    >
      <p className="muted">
        {subs.toLocaleString('en-GB')} subs waiting. Add the frames below or change the rig in Settings →
        Rigs.{' '}
        <Link to="/calibration/to-shoot" search={query}>
          What to shoot
        </Link>{' '}
        groups them into the frames to take.
      </p>
      <div className={s.pane}>
        <ul className={s.blockList}>
          {visible.map((b) => (
            <li key={`${b.dataset_id}-${b.night}-${b.needs.join()}`}>
              <VerdictBadge state="await" label={`${b.subs} sub${b.subs === 1 ? '' : 's'}`} />
              <div>
                <Link to="/datasets/$id" params={{ id: String(b.dataset_id) }}>
                  <strong>
                    {b.collection} · {b.dataset}
                  </strong>
                </Link>{' '}
                is waiting for a {b.waiting_for}
                {b.night ? ` · ${nightText(b.night)}` : ''}
                <div className="muted">Looking for: {b.needs.join('; ')}</div>
              </div>
            </li>
          ))}
        </ul>
        <LoadMore hasMore={hasMore} loading={false} onMore={more} />
      </div>
    </Collapsible>
  )
}

/** 002 C11: calibrated subs whose match now names different masters; re-calibrated only when you say so. */
function NewerCalibration({ scope }: { scope: Scope }) {
  const query = scopeQuery(scope)
  const q = useQuery({
    queryKey: ['calibration-recalibration', query],
    queryFn: async () => unwrap(await api.GET('/calibration/recalibration', { params: { query } })),
  })
  const rows = q.data ?? []
  const { visible, hasMore, more } = useProgressive(rows, 30)
  if (!rows.length) return null
  return (
    <Collapsible
      id="calibration-newer"
      title="Newer calibration available"
      meta={`${rows.length} dataset${rows.length === 1 ? '' : 's'}`}
      className={s.blocking}
    >
      <p className="muted">Re-calibrate from the dataset's Calibration tab.</p>
      <div className={s.pane}>
        <ul className={s.blockList}>
          {visible.map((r) => (
            <li key={r.dataset_id}>
              <VerdictBadge state="await" label={`${r.subs} sub${r.subs === 1 ? '' : 's'}`} />
              <div>
                <Link
                  to="/datasets/$id"
                  params={{ id: String(r.dataset_id) }}
                  search={{ tab: 'calibration' }}
                >
                  <strong>
                    {r.collection ? `${r.collection} · ` : ''}
                    {r.dataset}
                  </strong>
                </Link>
                <div className="muted">
                  {r.sessions} session{r.sessions === 1 ? '' : 's'}
                </div>
              </div>
            </li>
          ))}
        </ul>
        <LoadMore hasMore={hasMore} loading={false} onMore={more} />
      </div>
    </Collapsible>
  )
}

/** 002 C13: the nights a master may calibrate (e.g. flats from before a camera rotation). Saving rematches. */
function WindowEditor({ sha, from, to }: { sha: string; from: string; to: string }) {
  const qc = useQueryClient()
  const [open, setOpen] = useState(false)
  const [a, setA] = useState(from)
  const [b, setB] = useState(to)
  const save = useMutation({
    mutationFn: async (body: { valid_from: string | null; valid_to: string | null }) =>
      unwrap(await api.PUT('/masters/{sha256}/window', { params: { path: { sha256: sha } }, body })),
    scope: { id: `master-${sha}` },
    meta: { failed: "Couldn't save the window" },
    // the row shows the new nights at once and the editor closes; rematching follows in the background
    ...optimistic(qc, (body: { valid_from: string | null; valid_to: string | null }) => [
      [
        ['masters'],
        (o) =>
          patchItems<Master>(
            o,
            (m) => m.sha256 === sha,
            (m) => ({ ...m, ...body }),
          ),
      ],
    ]),
  })
  const put = (body: { valid_from: string | null; valid_to: string | null }) => {
    save.mutate(body)
    setOpen(false)
  }
  if (!open)
    return (
      <button
        type="button"
        className={ui.button}
        onClick={(e) => {
          e.stopPropagation()
          setOpen(true)
        }}
        title="Limit the nights this master calibrates"
      >
        Window…
      </button>
    )
  return (
    // the row opens the master on click; keep clicks in the editor here
    // oxlint-disable-next-line jsx-a11y/no-static-element-interactions, jsx-a11y/click-events-have-key-events
    <div className={s.windowEdit} onClick={(e) => e.stopPropagation()}>
      <input type="date" aria-label="Use from" value={a} onChange={(e) => setA(e.target.value)} />
      <input
        type="date"
        aria-label="Use until"
        value={b}
        min={a || undefined}
        onChange={(e) => setB(e.target.value)}
      />
      <button
        type="button"
        className={ui.button}
        onClick={() => put({ valid_from: a || null, valid_to: b || null })}
      >
        Save
      </button>
      <button
        type="button"
        className={ui.button}
        onClick={() => {
          setA('')
          setB('')
          put({ valid_from: null, valid_to: null })
        }}
      >
        Clear
      </button>
      <button type="button" className={ui.button} onClick={() => setOpen(false)}>
        Cancel
      </button>
    </div>
  )
}

const TABS: [string, string, (m: Master) => boolean][] = [
  ['all', 'All', () => true],
  ['dark', 'Darks', (m) => m.frame_type === 'master_dark'],
  ['flat', 'Flats', (m) => m.frame_type === 'master_flat'],
  ['bias', 'Bias', (m) => m.frame_type === 'master_bias' || m.frame_type === 'master_dark_flat'],
]

/** One table of masters, built and imported (002-DR-03/04): what each matches, who uses it, and its state. */
function MastersTable({
  masters,
  filterKey,
  onOpen,
  loading,
}: {
  masters: Master[]
  filterKey: string
  onOpen: (sha: string) => void
  loading?: boolean
}) {
  const [tab, setTab] = useState('all')
  const qc = useQueryClient()
  // retiring is an ignore rule on the file (002 C13): recorded with who and when, undone in Settings → Ignored
  const retire = useMutation({
    mutationFn: async (sha: string) =>
      unwrap(
        await api.POST('/ignore-rules', {
          body: { kind: 'content', value: sha, note: 'Retired master' },
        }),
      ),
    scope: { id: 'ignore-rules' },
    meta: { failed: "Couldn't retire the master" },
    ...optimistic(
      qc,
      (sha: string) => [
        [
          ['masters'],
          (o) =>
            patchItems<Master>(
              o,
              (m) => m.sha256 === sha,
              () => null,
            ),
        ],
      ],
      () => [['ignore-rules']],
    ),
  })
  const pick = TABS.find((t) => t[0] === tab)![2]
  const { sorted, th, sort } = useSort(masters.filter(pick), {
    type: (m) => TYPE[m.frame_type] ?? m.frame_type,
    matches: (m) => [m.filter, m.exptime_s, m.gain].filter((x) => x != null).join(' '),
    frames: (m) => m.frames,
    created: (m) => m.night,
    used: (m) => m.used_sessions,
    state: (m) => m.state,
  })
  // sorted and filtered first, then shown a slice at a time as the pane scrolls
  const {
    visible: rows,
    hasMore,
    more,
  } = useProgressive(sorted, 60, `${filterKey}|${tab}|${sort?.key}|${sort?.desc}`)
  return (
    <Collapsible id="calibration-masters" title="Masters" meta={masters.length.toLocaleString('en-GB')}>
      <div className={s.tabs} role="tablist" aria-label="Master type">
        {TABS.map(([k, label, f]) => (
          <button
            key={k}
            type="button"
            role="tab"
            aria-selected={tab === k}
            className={s.tab}
            onClick={() => setTab(k)}
          >
            {label} <span className="mono">{masters.filter(f).length}</span>
          </button>
        ))}
      </div>
      {loading ? (
        <Spinner label="Loading masters" />
      ) : rows.length === 0 ? (
        <EmptyState title="No masters here">Build missing masters, or add masters made elsewhere.</EmptyState>
      ) : (
        <div className={`${s.tableWrap} ${s.pane}`}>
          <table className={ui.table}>
            <thead>
              <tr>
                <th>
                  <span className="visually-hidden">Preview</span>
                </th>
                {th('type', 'Type')}
                {th('matches', 'Matches')}
                {th('frames', 'Frames', s.num)}
                {th('created', 'Created', s.nowrap)}
                {th('used', 'Used by')}
                {th('state', 'State')}
                <th className={s.actions}>
                  <span className="visually-hidden">Actions</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {rows.map((m) => (
                <tr
                  key={m.sha256}
                  className={s.clickable}
                  tabIndex={0}
                  onClick={() => onOpen(m.sha256)}
                  onKeyDown={(e) => e.key === 'Enter' && onOpen(m.sha256)}
                >
                  <td className={s.thumbCell}>
                    <Zoomable
                      target={{ kind: 'sub', sha: m.sha256 }}
                      name={TYPE[m.frame_type] ?? m.frame_type}
                    >
                      {m.thumb ? (
                        <img src={m.thumb} alt="" loading="lazy" />
                      ) : (
                        <span className="muted">View</span>
                      )}
                    </Zoomable>
                  </td>
                  <td>{TYPE[m.frame_type] ?? m.frame_type}</td>
                  <td>
                    <span className="mono">
                      {[
                        m.filter,
                        m.exptime_s != null && m.frame_type !== 'master_bias' ? `${m.exptime_s} s` : null,
                        m.gain != null ? `gain ${m.gain}` : null,
                        m.set_temp_c != null ? temp(m.set_temp_c) : null,
                      ]
                        .filter(Boolean)
                        .join(' · ')}
                    </span>
                    <div className="muted">{rigOf(m)}</div>
                  </td>
                  <td className={`mono ${s.num}`}>
                    {m.built_set_id ? (
                      <Link
                        to="/calibration/sets/$id"
                        params={{ id: String(m.built_set_id) }}
                        onClick={(e) => e.stopPropagation()}
                      >
                        {m.frames ?? '—'}
                      </Link>
                    ) : (
                      (m.frames ?? '—')
                    )}
                  </td>
                  <td className={s.nowrap}>{m.night ? nightText(m.night) : '—'}</td>
                  <td>
                    {m.used_sessions
                      ? `${m.used_datasets} dataset${m.used_datasets === 1 ? '' : 's'} · ${m.used_sessions} session${m.used_sessions === 1 ? '' : 's'}`
                      : '—'}
                  </td>
                  <td>
                    {m.missing.length > 0 ? (
                      <Link to="/reconcile" onClick={(e) => e.stopPropagation()}>
                        <VerdictBadge state="recon" label={`Needs ${m.missing.join(', ')}`} />
                      </Link>
                    ) : (
                      <span className={m.state === 'Current' ? undefined : 'muted'}>{m.state}</span>
                    )}
                    {(m.valid_from || m.valid_to) && (
                      <div className="muted">
                        Used {m.valid_from ? `from ${nightText(m.valid_from)}` : ''}
                        {m.valid_from && m.valid_to ? ' ' : ''}
                        {m.valid_to ? `until ${nightText(m.valid_to)}` : ''}
                      </div>
                    )}
                  </td>
                  <td className={s.actions}>
                    {/* one line per row: the two actions side by side, never stacked */}
                    <div className={s.rowActions}>
                      <WindowEditor sha={m.sha256} from={m.valid_from ?? ''} to={m.valid_to ?? ''} />
                      <ConfirmButton
                        className={ui.button}
                        question={<>Retire this master? Lights using it will rematch.</>}
                        confirm="Retire"
                        onConfirm={() => retire.mutate(m.sha256)}
                      >
                        Retire
                      </ConfirmButton>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <LoadMore hasMore={hasMore} loading={false} onMore={more} />
        </div>
      )}
    </Collapsible>
  )
}
