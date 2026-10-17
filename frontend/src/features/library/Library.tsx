// Library (spec 006; design v2 L1): readouts, collections as cards with integration per filter, then datasets
// not in a collection with SubStation's suggestion.
import { Link, useNavigate } from '@tanstack/react-router'
import { useQuery } from '@tanstack/react-query'
import { useMemo, useState } from 'react'
import { Button, EmptyState, ErrorState, Skeleton, Spinner } from '../../components/ui'
import { VerdictBadge, type VerdictState } from '../../components/VerdictBadge'
import { integrationText, monthSpan, nightText } from '../format'
import {
  stackPreviewUrl,
  useCollectionActions,
  useLibrary,
  useLiveRefresh,
  type Card,
  type LibDataset,
} from '../v2/hooks'
import { useReconCounts } from '../metadata/queries'
import { api, unwrap } from '../../api/client'
import v from '../v2/v2.module.css'
import s from './library.module.css'
import { collectionFacts, nameParts } from './names'
import tb from './tables.module.css'
import { Collapsible } from '../../components/Collapsible'
import { LoadMore } from '../../components/LoadMore'
import { useProgressive } from '../../components/useProgressive'
import { ScopeBar } from '../scope/ScopeBar'
import { isEmpty, scopeParams, scopeQuery, type Scope } from '../scope/scope'
import { useScope } from '../scope/useScope'
import { ChooseBox, useChosen } from '../../components/BulkBar'
import { DatasetBulkBar } from './DatasetBulkBar'

const STATE_LABEL: Record<string, [VerdictState, string]> = {
  integ: ['integ', 'Integrating'],
  stale: ['stale', 'Master stale'],
  await: ['await', 'Awaiting calibration'],
  recon: ['recon', 'Needs reconciliation'],
  failed: ['reject', 'Master failed'],
}

type Readouts = {
  needs_you?: { review: number; reconcile: number; stale: number }
  missing_calibration?: { subs: number; top: { reason: string; subs: number }[] }
  ready_to_stack?: { datasets: number; top: { id: number; name: string; new: number }[] }
  this_month?: { hours: number; nights: number; last: { hours: number; nights: number } }
}

export function Library() {
  useLiveRefresh()
  // the filters are the shared scope, in the address (spec 018): the server narrows the lists and the totals
  const [scope, setScope] = useScope()
  const q = useLibrary(scope)
  const d = q.data
  // the whole library (the same request when nothing is filtered): whether it's empty, every collection a dataset
  // can join, and every filter to choose from, whatever is filtered now (review 2026-10-15)
  const whole = useLibrary({}).data
  const base = whole ?? d
  const filters = useMemo(
    () =>
      [
        ...new Set([
          ...(base?.collections ?? []).flatMap((c) => Object.keys(c.filters)),
          ...(base?.ungrouped ?? []).map((u) => u.dataset.filter ?? ''),
        ]),
      ].filter((f) => f && f !== '?'),
    [base],
  )
  if (q.isError)
    return (
      <ErrorState title="Couldn't load the library" onRetry={() => q.refetch()}>
        {q.error.message}
      </ErrorState>
    )
  if (!d)
    return (
      <div className={v.page} aria-busy="true">
        <Skeleton width={220} height={32} />
        <Skeleton height={140} />
        <Skeleton height={220} />
      </div>
    )
  const cards = d.collections
  const ungrouped = d.ungrouped
  const scoped = !isEmpty(scope)
  const resetKey = scopeParams(scope)
  const r = d.readouts as Readouts
  const needs = r.needs_you ?? { review: 0, reconcile: 0, stale: 0 }
  const needsTotal = needs.review + needs.reconcile + needs.stale
  const missing = r.missing_calibration ?? { subs: 0, top: [] }
  const ready = r.ready_to_stack ?? { datasets: 0, top: [] }
  const month = r.this_month ?? { hours: 0, nights: 0, last: { hours: 0, nights: 0 } }
  const empty = (whole ?? d).counts.datasets === 0

  return (
    <div className={v.page}>
      <ReconcileNotice />
      <header className={v.head}>
        <div>
          <h1>Library</h1>
          <div className={v.sub}>
            {d.counts.datasets} datasets in {d.counts.collections} collection
            {d.counts.collections === 1 ? '' : 's'}
            {d.counts.ungrouped ? `, ${d.counts.ungrouped} ungrouped` : ''} · {d.rigs} rig
            {d.rigs === 1 ? '' : 's'}
          </div>
        </div>
        <div className={v.actions}>
          <NewCollection />
        </div>
      </header>

      <ScopeBar
        scope={scope}
        onChange={setScope}
        filters={filters}
        search="Search objects, rigs, filters, months"
      />

      <Stats scope={scope} />

      {/* what's worth knowing on opening SubStation (owner 2026-10-13): what to do next, not machine status */}
      <div className={v.readouts}>
        <Link to={needs.review ? '/review' : needs.reconcile ? '/reconcile' : '/'} className={v.readout}>
          <div className={v.readoutLabel}>Needs you</div>
          <div className={`${v.readoutValue} ${needsTotal ? v.accentValue : ''}`}>
            {needsTotal.toLocaleString('en-GB')}
          </div>
          <div className={v.readoutDetail}>
            {needsTotal
              ? [
                  needs.review ? `${needs.review.toLocaleString('en-GB')} to review` : '',
                  needs.reconcile ? `${needs.reconcile.toLocaleString('en-GB')} to reconcile` : '',
                  needs.stale ? `${needs.stale} stack${needs.stale === 1 ? '' : 's'} out of date` : '',
                ]
                  .filter(Boolean)
                  .join(' · ')
              : 'nothing waiting'}
          </div>
        </Link>
        <Link to="/calibration" className={v.readout}>
          <div className={v.readoutLabel}>Missing calibration</div>
          <div className={v.readoutValue}>{missing.subs.toLocaleString('en-GB')}</div>
          <div className={v.readoutDetail}>
            {missing.subs ? (
              <>
                subs waiting
                {missing.top.slice(0, 2).map((m) => (
                  <div key={m.reason} className={v.muted}>
                    {m.reason} ({m.subs.toLocaleString('en-GB')})
                  </div>
                ))}
              </>
            ) : (
              'every sub has its calibration'
            )}
          </div>
        </Link>
        <div className={v.readout}>
          <div className={v.readoutLabel}>Ready to stack</div>
          <div className={v.readoutValue}>{ready.datasets.toLocaleString('en-GB')}</div>
          <div className={v.readoutDetail}>
            {ready.top.length
              ? ready.top.slice(0, 2).map((x) => (
                  <div key={x.id}>
                    <Link to="/datasets/$id" params={{ id: String(x.id) }}>
                      {x.name}
                    </Link>{' '}
                    <span className={v.muted}>+{x.new.toLocaleString('en-GB')} subs</span>
                  </div>
                ))
              : 'nothing new since the last stacks'}
          </div>
        </div>
        <div className={v.readout}>
          <div className={v.readoutLabel}>This month</div>
          <div className={v.readoutValue}>{integrationText(month.hours * 3600)}</div>
          <div className={v.readoutDetail}>
            {month.nights} night{month.nights === 1 ? '' : 's'} · last month{' '}
            {integrationText(month.last.hours * 3600)} over {month.last.nights}
          </div>
        </div>
      </div>

      {empty && <FirstRun />}

      {scoped && !empty && !cards.length && !ungrouped.length && (
        <EmptyState title="Nothing matches these filters">
          Widen the nights, choose another rig or filter, or clear the filters.
        </EmptyState>
      )}

      {/* the slices start again from the top when the filters change */}
      <CollectionCards cards={cards} scope={scope} resetKey={resetKey} />
      <UngroupedList rows={ungrouped} collections={(whole ?? d).collections} resetKey={resetKey} />
    </div>
  )
}

// where a collection's files are (spec 013 FR-009): the Library's own filter, shown once libraries have roles
const WHERE: [string, string][] = [
  ['', 'Anywhere'],
  ['active', 'In the active library'],
  ['archive', 'In the archive'],
  ['both', 'Split across both'],
  ['suggested', 'Worth archiving'],
]
const WHERE_PILL: Record<string, string> = { archive: 'Archived', both: 'Partly archived' }

export function byWhere(cards: Card[], where: string): Card[] {
  if (!where) return cards
  if (where === 'suggested') return cards.filter((c) => c.archive_suggested)
  return cards.filter((c) => c.files_where === where)
}

function CollectionCards({ cards: all, scope, resetKey }: { cards: Card[]; scope: Scope; resetKey: string }) {
  const navigate = useNavigate()
  const [where, setWhere] = useState('')
  // a collection opens with the Library's filters, so its links (the map, a night) carry them on (spec 018)
  const carry = scopeQuery(scope)
  const cards = byWhere(all, where)
  const { visible, hasMore, more } = useProgressive(cards, 24, `${resetKey}|${where}`)
  const roles = all.some((c) => c.files_where)
  if (!all.length) return null
  return (
    <Collapsible id="library-collections" title="Collections" meta={cards.length}>
      {roles && (
        <label className={s.whereFilter}>
          Files{' '}
          <select value={where} onChange={(e) => setWhere(e.target.value)}>
            {WHERE.map(([k, label]) => (
              <option key={k} value={k}>
                {label}
                {k === 'suggested' ? ` (${all.filter((c) => c.archive_suggested).length})` : ''}
              </option>
            ))}
          </select>
        </label>
      )}
      {!cards.length && <p className={v.muted}>No collection matches.</p>}
      <div className={s.cards}>
        {visible.map((c) => (
          <CollectionCardView
            key={c.id}
            c={c}
            carry={carry}
            onOpen={() =>
              void navigate({ to: '/collections/$id', params: { id: String(c.id) }, search: carry })
            }
          />
        ))}
      </div>
      <LoadMore hasMore={hasMore} loading={false} onMore={more} />
    </Collapsible>
  )
}

/** Datasets not in a collection: a long list, so it scrolls in its own pane and loads as it scrolls. */
function UngroupedList({
  rows,
  collections,
  resetKey,
}: {
  rows: LibDataset[]
  collections: Card[]
  resetKey: string
}) {
  const actions = useCollectionActions()
  const { visible, hasMore, more } = useProgressive(rows, 60, resetKey)
  // spec 016 U6: choose several and re-grade, stack or move them together
  const shownIds = useMemo(() => rows.map((u) => u.dataset.id), [rows])
  const pick = useChosen<number>(shownIds)
  if (!rows.length) return null
  return (
    <div className={`${v.card} ${tb.flush}`}>
      <Collapsible
        id="library-ungrouped"
        title="Not in a collection"
        meta={
          <span className={s.ungroupedHead}>
            {rows.length.toLocaleString('en-GB')}
            <Button onClick={() => actions.acceptAll.mutate()} disabled={actions.acceptAll.isPending}>
              {actions.acceptAll.isPending ? 'Accepting…' : 'Accept every suggestion'}
            </Button>
          </span>
        }
      >
        <DatasetBulkBar
          chosen={pick.chosen}
          onClear={pick.clear}
          shown={rows.length}
          onChooseShown={() =>
            pick.setAll(
              rows.map((u) => u.dataset.id),
              true,
            )
          }
          from={null}
        />
        <div className={tb.pane}>
          {visible.map((u) => (
            <UngroupedRow
              key={u.dataset.id}
              u={u}
              collections={collections}
              chosen={pick.chosen.has(u.dataset.id)}
              onChoose={() => pick.toggle(u.dataset.id)}
            />
          ))}
          <LoadMore hasMore={hasMore} loading={false} onMore={more} />
        </div>
      </Collapsible>
    </div>
  )
}

function CollectionCardView({
  c,
  carry,
  onOpen,
}: {
  c: Card
  carry: Record<string, string | number>
  onOpen: () => void
}) {
  // every sub counts, calibrated or not: the bar is all that was captured, split into usable, still waiting
  // (for calibration or grading) and rejected
  const time = Object.fromEntries(
    Object.entries(c.filters).map(([f, a]) => [
      f,
      c.filter_time?.[f] ?? { total_s: a, accepted_s: a, rejected_s: 0 },
    ]),
  )
  const max = Math.max(1, ...Object.values(time).map((t) => t.total_s))
  const captured = Object.values(time).reduce((n, t) => n + t.total_s, 0)
  return (
    <article className={`${v.card} ${s.card}`}>
      <button className={s.preview} onClick={onOpen} aria-label={`Open ${c.name}`}>
        {c.preview_master ? (
          <img src={stackPreviewUrl(c.preview_master)} alt="" />
        ) : (
          <span className="mono">master preview</span>
        )}
      </button>
      <div className={s.cardBody}>
        <h2 className={s.cardTitle}>
          <Link to="/collections/$id" params={{ id: String(c.id) }} search={carry}>
            {nameParts(c.name).title}
          </Link>
          {nameParts(c.name).designation && (
            <span className={s.designation}>{nameParts(c.name).designation}</span>
          )}
        </h2>
        <div className={v.muted}>{collectionFacts(c)}</div>
        <div className={v.pills}>
          {c.rigs.map((r) => (
            <Link
              key={r}
              to="/settings"
              hash="rigs"
              className={v.pill}
              title={`Rename or merge ${r} in Settings → Rigs`}
            >
              {r}
            </Link>
          ))}
        </div>
        <div className={s.bars}>
          {Object.entries(time)
            .sort((a, b) => b[1].total_s - a[1].total_s)
            .map(([f, t]) => {
              const waiting = Math.max(0, t.total_s - t.accepted_s - t.rejected_s)
              const pct = (x: number) => `${(x / max) * 100}%`
              return (
                <div
                  key={f}
                  className={s.barRow}
                  title={`${f}: ${integrationText(t.total_s)} captured · ${integrationText(t.accepted_s)} usable · ${integrationText(waiting)} waiting for calibration or grading · ${integrationText(t.rejected_s)} rejected`}
                >
                  <span>{f}</span>
                  <span className={s.bar}>
                    <span className={s.barOk} style={{ width: pct(t.accepted_s) }} />
                    <span className={s.barWait} style={{ width: pct(waiting) }} />
                    <span className={s.barRej} style={{ width: pct(t.rejected_s) }} />
                  </span>
                  <span className={v.mono}>
                    {c.goals?.[f] ? (
                      <span title={`Goal: ${c.goals[f]} h of usable integration`}>
                        {integrationText(t.accepted_s)} / {c.goals[f]}h
                      </span>
                    ) : (
                      integrationText(t.total_s)
                    )}
                  </span>
                </div>
              )
            })}
        </div>
        <div className={s.cardFoot}>
          <span className={v.muted}>
            {monthSpan(c.first_night, c.last_night)} · {c.sessions} session{c.sessions === 1 ? '' : 's'}
          </span>
          <span className={v.mono} title="Usable (graded and kept) of everything captured">
            <span className={v.accent}>{integrationText(c.accepted_integration_s)}</span>
            {captured > c.accepted_integration_s && (
              <span className={v.muted}> of {integrationText(captured)}</span>
            )}
          </span>
        </div>
        {(c.states.length > 0 || WHERE_PILL[c.files_where ?? ''] || c.archive_suggested) && (
          <div className={v.pills}>
            {WHERE_PILL[c.files_where ?? ''] && (
              <span className={v.pill}>{WHERE_PILL[c.files_where ?? '']}</span>
            )}
            {c.archive_suggested && <span className={v.pill}>Worth archiving</span>}
            {c.states.map(
              (st) =>
                STATE_LABEL[st] && (
                  <VerdictBadge key={st} state={STATE_LABEL[st][0]} label={STATE_LABEL[st][1]} />
                ),
            )}
          </div>
        )}
      </div>
    </article>
  )
}

function UngroupedRow({
  u,
  collections,
  chosen,
  onChoose,
}: {
  u: LibDataset
  collections: Card[]
  chosen: boolean
  onChoose: () => void
}) {
  const actions = useCollectionActions()
  const [choice, setChoice] = useState('')
  const [newName, setNewName] = useState('')
  const sug = u.suggestion as { collection_id: number | null; name: string; why: string } | null
  const busy = actions.add.isPending || actions.create.isPending
  const ds = u.dataset
  return (
    <div className={s.ungrouped}>
      <div className={s.ungroupedName}>
        <ChooseBox checked={chosen} onChange={onChoose} label={`Select ${ds.target} · ${u.label}`} />
        <div>
          <Link to="/datasets/$id" params={{ id: String(ds.id) }} className={s.dsName}>
            {ds.target} · {u.label}
          </Link>
          <div className={v.muted}>
            {u.sessions} session{u.sessions === 1 ? '' : 's'} · {ds.sub_count.toLocaleString('en-GB')} subs
            {ds.sub_count && Number.isInteger(Math.round((ds.integration_s / ds.sub_count) * 10) / 10)
              ? ` × ${Math.round(ds.integration_s / ds.sub_count)} s`
              : ''}
            {ds.first_utc
              ? ds.last_night && ds.last_night !== ds.first_utc.slice(0, 10)
                ? ` · from ${nightText(ds.first_utc.slice(0, 10))} to ${nightText(ds.last_night)}`
                : ` · ${nightText(ds.first_utc.slice(0, 10))}`
              : ''}
          </div>
        </div>
      </div>
      <span className={`${v.mono} ${v.accent}`}>{integrationText(ds.integration_s)}</span>
      <span className={v.note}>
        {sug ? (sug.collection_id ? `Suggested: ${sug.name}. ${sug.why}` : sug.why) : ''}
      </span>
      <div className={v.actions}>
        <select
          className={v.select}
          value={choice}
          onChange={(e) => setChoice(e.target.value)}
          aria-label="Choose a collection"
        >
          <option value="">Choose…</option>
          <option value="new">New collection…</option>
          {collections.map((c) => (
            <option key={c.id} value={c.id}>
              {c.name}
            </option>
          ))}
        </select>
        {choice === 'new' ? (
          <form
            className={v.actions}
            onSubmit={(e) => {
              e.preventDefault()
              if (newName.trim()) actions.create.mutate({ name: newName.trim(), dataset_ids: [ds.id] })
            }}
          >
            <input
              className={v.input}
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              placeholder="Collection name, e.g. Soul Nebula"
              aria-label="New collection name"
            />
            <Button type="submit" variant="primary" disabled={busy || !newName.trim()}>
              Create
            </Button>
          </form>
        ) : choice ? (
          <Button
            disabled={busy}
            onClick={() => actions.add.mutate({ id: Number(choice), dataset_ids: [ds.id] })}
          >
            Add
          </Button>
        ) : sug?.collection_id ? (
          <Button
            variant="primary"
            disabled={busy}
            onClick={() => actions.add.mutate({ id: sug.collection_id!, dataset_ids: [ds.id] })}
          >
            Add to {sug.name}
          </Button>
        ) : (
          <Button
            variant="primary"
            disabled={busy}
            onClick={() => actions.create.mutate({ name: sug?.name || ds.target, dataset_ids: [ds.id] })}
          >
            New collection
          </Button>
        )}
      </div>
    </div>
  )
}

/** Reconciliation is reached from here rather than the header (001-DR-03). */
function ReconcileNotice() {
  const counts = useReconCounts()
  const n = Object.entries(counts.data ?? {})
    .filter(([k]) => k !== 'bad_without_twin')
    .reduce((a, [, x]) => a + x, 0)
  if (!n) return null
  return (
    <div className={v.banner}>
      <VerdictBadge state="recon" label="Needs reconciliation" />
      <span>
        {n.toLocaleString('en-GB')} item{n === 1 ? '' : 's'} blocking grading.
      </span>
      <Link to="/reconcile" className={v.pill}>
        Open reconciliation
      </Link>
    </div>
  )
}

/** First run (001-DR-01): what is being watched, and where to go from here. */
function FirstRun() {
  const libs = useQuery({ queryKey: ['libraries'], queryFn: async () => unwrap(await api.GET('/libraries')) })
  return (
    <EmptyState title="No subs yet">
      <p>
        Watching{' '}
        {(libs.data ?? [])
          .filter((l) => l.enabled)
          .map((l) => (
            <span key={l.id} className={v.mono}>
              {l.mount_path}{' '}
            </span>
          ))}
      </p>
      <p>New FITS and XISF files appear here.</p>
      <div className={v.actions}>
        <Link to="/settings" hash="folders" className={v.pill}>
          Change watched folders
        </Link>
        <Link to="/settings" hash="patterns" className={v.pill}>
          Import an existing archive
        </Link>
      </div>
    </EmptyState>
  )
}

/** New collection (006-DR-01): name it here, then add datasets from its page. */
function NewCollection() {
  const [name, setName] = useState<string | null>(null)
  const actions = useCollectionActions()
  const navigate = useNavigate()
  if (name === null)
    return (
      <Button variant="primary" onClick={() => setName('')}>
        New collection
      </Button>
    )
  return (
    <form
      className={v.actions}
      onSubmit={(e) => {
        e.preventDefault()
        if (!name.trim()) return
        actions.create.mutate(
          { name: name.trim(), dataset_ids: [] },
          { onSuccess: (c) => void navigate({ to: '/collections/$id', params: { id: String(c.id) } }) },
        )
      }}
    >
      <input
        className={v.input}
        value={name}
        onChange={(e) => setName(e.target.value)}
        placeholder="Name, e.g. Heart and Soul"
        aria-label="New collection name"
      />
      <Button type="submit" variant="primary" disabled={!name.trim() || actions.create.isPending}>
        {/* the page opens once the server has given it an id */}
        {actions.create.isPending ? 'Creating…' : 'Create'}
      </Button>
      <Button onClick={() => setName(null)}>Cancel</Button>
    </form>
  )
}

/** What the filters cover (owner 2026-10-10): lights taken, hours per filter and rig, kept and rejected, SQM.
 * Worked out on the server for the shared scope (spec 018 FR-006); the search box settles before it asks. */
function Stats({ scope }: { scope: Scope }) {
  const query = scopeQuery(scope)
  const st = useQuery({
    queryKey: ['library-stats', query],
    queryFn: async () => unwrap(await api.GET('/library/stats', { params: { query } })),
    placeholderData: (prev) => prev,
  })
  const d = st.data
  if (!d) return <Skeleton height={168} />
  const updating = st.isFetching && st.isPlaceholderData
  const filtered = Object.keys(query).length > 0
  const pct = (x: number | null | undefined) => (x == null ? '—' : `${Math.round(x * 100)}%`)
  const bars = (title: string, rows: Record<string, number>) => {
    const max = Math.max(1e-9, ...Object.values(rows))
    return (
      <div className={s.statBars}>
        <span className={v.sectionLabel}>{title}</span>
        {Object.entries(rows).map(([k, h]) => (
          <div key={k} className={s.statRow}>
            <span>{k}</span>
            <span className={s.statBar}>
              <span style={{ width: `${(h / max) * 100}%` }} />
            </span>
            <span className={v.mono}>{integrationText(h * 3600)}</span>
          </div>
        ))}
      </div>
    )
  }
  return (
    <section
      className={`${v.card} ${v.cardPad} ${s.stats} ${updating ? s.updating : ''}`}
      aria-label="Totals for the filters"
      aria-busy={updating}
    >
      {updating && (
        <span className={s.statSpin}>
          <Spinner label="Updating totals" />
        </span>
      )}
      <Collapsible
        id="library-stats"
        title={filtered ? 'Totals for the filters' : 'Totals'}
        meta={`${d.frames.toLocaleString('en-GB')} lights`}
      >
        <div className={s.statsBody}>
          <div className={s.statNums}>
            <div>
              <span className={v.sectionLabel}>{filtered ? 'Filtered' : 'All'} lights</span>
              <strong className={v.mono}>{d.frames.toLocaleString('en-GB')}</strong>
              <span className={v.muted}>
                {d.nights} night{d.nights === 1 ? '' : 's'}
              </span>
            </div>
            <div>
              <span className={v.sectionLabel}>Hours taken</span>
              <strong className={v.mono}>{integrationText(d.hours * 3600)}</strong>
              <span className={v.muted}>{integrationText(d.accepted_hours * 3600)} kept</span>
            </div>
            <div>
              <span className={v.sectionLabel}>Kept</span>
              <strong className={`${v.mono} ${v.ok}`}>{pct(d.success_rate)}</strong>
              <span className={v.muted}>of {d.graded.toLocaleString('en-GB')} graded</span>
            </div>
            <div>
              <span className={v.sectionLabel}>Rejected</span>
              <strong className={`${v.mono} ${v.bad}`}>
                {/* kept + rejected is every graded sub: rounded on its own each could make 101% */}
                {d.success_rate != null && d.failure_rate != null
                  ? `${100 - Math.round(d.success_rate * 100)}%`
                  : pct(d.failure_rate)}
              </strong>
              <span className={v.muted}>cloud, seeing, tracking</span>
            </div>
            <div>
              <span className={v.sectionLabel}>Average SQM</span>
              <strong className={v.mono}>{d.avg_sqm != null ? d.avg_sqm.toFixed(2) : '—'}</strong>
              <span className={v.muted}>
                {d.sqm_subs ? `from ${d.sqm_subs.toLocaleString('en-GB')} subs` : 'not recorded'}
              </span>
            </div>
          </div>
          <div className={s.statGrid}>
            {bars('Hours per filter', d.by_filter)}
            {bars('Hours per rig', d.by_rig)}
          </div>
        </div>
      </Collapsible>
    </section>
  )
}
