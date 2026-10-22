// Library (spec 006; design v2 L1): readouts, collections as cards with integration per filter, then datasets
// not in a collection with SubStation's suggestion.
import { Link, useNavigate, useSearch } from '@tanstack/react-router'
import { WHERE_LABEL } from '../changes/putAway'
import { useQuery } from '@tanstack/react-query'
import { useMemo, useState } from 'react'
import {
  BarMeter,
  Button,
  buttonClass,
  Chip,
  EmptyState,
  ErrorState,
  Field,
  FilterMeter,
  FilterMeterLegend,
  GradeMeter,
  Input,
  Select,
  Skeleton,
  Spinner,
  StatGrid,
  StatTile,
} from '../../components/ui'
import { Help } from '../../components/Help'
import { sortFilters } from '../../components/filters'
import { VerdictBadge, type VerdictState } from '../../components/VerdictBadge'
import { countText, exposureText, integrationText, monthSpan, nightText, numText, plural } from '../format'
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
  const empty = (whole ?? d).counts.datasets === 0

  return (
    <div className={v.page}>
      <ReconcileNotice />
      <header className={v.head}>
        <div>
          <h1>Library</h1>
          <div className={v.sub}>
            {plural(d.counts.datasets, 'dataset')} in {plural(d.counts.collections, 'collection')}
            {d.counts.ungrouped ? `, ${countText(d.counts.ungrouped)} ungrouped` : ''} ·{' '}
            {plural(d.rigs, 'rig')}
          </div>
        </div>
        <div className={v.actions}>
          <NewCollection />
        </div>
      </header>

      {/* one search: the header's (C38). The bar narrows by rig, filter and nights */}
      <ScopeBar scope={scope} onChange={setScope} filters={filters} />

      <Stats scope={scope} />

      {/* what's worth knowing on opening SubStation (owner 2026-10-13): what to do next, not machine status. The
          server works these out for the whole library, so with filters on they say so rather than pretend (B03) */}
      <Readouts r={d.readouts as Readouts} scoped={scoped} />

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

// where a collection's files are (spec 013 FR-009, 006-DR-40): the Library's Show filter, in the address (?show=).
// Current, the default, leaves out collections whose files are all archived; a line under the cards says how many.
export type Show = 'current' | 'partly' | 'archived' | 'worth' | 'all'
export const SHOWS: [Show, string][] = [
  ['current', 'Current'],
  ['partly', WHERE_LABEL.both],
  ['archived', WHERE_LABEL.archive],
  ['worth', WHERE_LABEL.suggested],
  ['all', 'All'],
]
export const readShow = (x: unknown): Show | undefined =>
  SHOWS.some(([k]) => k === x) && x !== 'current' ? (x as Show) : undefined
const WHERE_PILL: Record<string, string> = { archive: WHERE_LABEL.archive, both: WHERE_LABEL.both }

export function byShow(cards: Card[], show: Show): Card[] {
  switch (show) {
    case 'current':
      return cards.filter((c) => c.files_where !== 'archive')
    case 'partly':
      return cards.filter((c) => c.files_where === 'both')
    case 'archived':
      return cards.filter((c) => c.files_where === 'archive')
    case 'worth':
      return cards.filter((c) => c.archive_suggested)
    default:
      return cards
  }
}

/** The Show choices with how many collections each would show; one that would show none can't be chosen. */
export function showOptions(cards: Card[], current: Show) {
  return SHOWS.map(([k, label]) => {
    const n = byShow(cards, k).length
    return { value: k, label: `${label} (${n})`, disabled: n === 0 && k !== current && k !== 'current' }
  })
}

function CollectionCards({ cards: all, scope, resetKey }: { cards: Card[]; scope: Scope; resetKey: string }) {
  const navigate = useNavigate()
  const search = useSearch({ strict: false }) as { show?: Show }
  const show: Show = search.show ?? 'current'
  const setShow = (next: Show) =>
    void navigate({
      to: '.',
      search: ((prev: Record<string, unknown>) => ({
        ...prev,
        show: next === 'current' ? undefined : next,
      })) as never,
      replace: true,
    })
  // a collection opens with the Library's filters, so its links (the map, a night) carry them on (spec 018)
  const carry = scopeQuery(scope)
  const cards = byShow(all, show)
  const { visible, hasMore, more } = useProgressive(cards, 24, `${resetKey}|${show}`)
  const roles = all.some((c) => c.files_where)
  const hidden = show === 'current' ? all.length - cards.length : 0
  if (!all.length) return null
  return (
    <Collapsible id="library-collections" title="Collections" meta={cards.length}>
      {roles && (
        <Field inline label="Show" className={s.whereFilter}>
          <Select
            size_="sm"
            value={show}
            onChange={(e) => setShow(e.target.value as Show)}
            options={showOptions(all, show)}
          />
        </Field>
      )}
      {!cards.length && <EmptyState inline>No collection matches.</EmptyState>}
      {cards.length > 0 && (
        <FilterMeterLegend goal={cards.some((c) => c.goals && Object.keys(c.goals).length > 0)} />
      )}
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
      {hidden > 0 && (
        <p className={s.hiddenLine}>
          {plural(hidden, 'archived collection')} hidden ·{' '}
          <Button size="sm" variant="link" onClick={() => setShow('all')}>
            Show
          </Button>
        </p>
      )}
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
            {countText(rows.length)}
            <Button
              size="sm"
              onClick={() => actions.acceptAll.mutate()}
              disabled={actions.acceptAll.isPending}
            >
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
  const { title, designation } = nameParts(c.name)
  return (
    <article className={`${v.card} ${s.card}`}>
      <button className={s.preview} onClick={onOpen} aria-label={`Open ${c.name}`}>
        {c.preview_master ? (
          <img src={stackPreviewUrl(c.preview_master)} alt="" />
        ) : (
          // no stack yet: the target's name, not a pattern that reads like progress (C04)
          <span className={s.previewName}>{designation || title}</span>
        )}
      </button>
      <div className={s.cardBody}>
        <h2 className={s.cardTitle}>
          <Link to="/collections/$id" params={{ id: String(c.id) }} search={carry}>
            {title}
          </Link>
          {designation && <span className={s.designation}>{designation}</span>}
        </h2>
        {/* the rig belongs in the facts line, not a chip of its own (D04) */}
        <div className={v.muted}>{[collectionFacts(c), ...c.rigs].join(' · ')}</div>
        <div className={s.bars}>
          {sortFilters(Object.keys(time)).map((f) => {
            const t = time[f]
            const waiting = Math.max(0, t.total_s - t.accepted_s - t.rejected_s)
            const goal = c.goals?.[f] ? c.goals[f] * 3600 : null
            return (
              <FilterMeter
                key={f}
                filter={f}
                kept={t.accepted_s}
                waiting={waiting}
                rejected={t.rejected_s}
                goal={goal}
                max={max}
                value={
                  goal
                    ? `${integrationText(t.accepted_s)} / ${integrationText(goal)}`
                    : integrationText(t.total_s)
                }
                detail={
                  goal
                    ? `${integrationText(t.accepted_s)} kept of a ${integrationText(goal)} goal`
                    : `${integrationText(t.accepted_s)} kept of ${integrationText(t.total_s)} captured`
                }
              />
            )
          })}
        </div>
        <div className={s.cardFoot}>
          <span className={v.muted}>
            {monthSpan(c.first_night, c.last_night)} · {plural(c.sessions, 'session')}
          </span>
          {/* labelled, not "3h 55m of 4h 30m" (D03) */}
          <span className={s.figure}>
            {integrationText(c.accepted_integration_s)} kept
            {captured > c.accepted_integration_s && (
              <span className={v.muted}> / {integrationText(captured)}</span>
            )}
          </span>
        </div>
        {(c.states.length > 0 || WHERE_PILL[c.files_where ?? ''] || c.archive_suggested) && (
          <div className={v.pills}>
            {WHERE_PILL[c.files_where ?? ''] && <Chip>{WHERE_PILL[c.files_where ?? '']}</Chip>}
            {c.archive_suggested && <Chip>{WHERE_LABEL.suggested}</Chip>}
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
  const sug = u.suggestion as { collection_id: number | null; name: string; why: string } | null
  // one choice, already on SubStation's suggestion: an existing collection, or a new one under a name (C37)
  const [choice, setChoice] = useState(sug?.collection_id ? String(sug.collection_id) : 'new')
  const [newName, setNewName] = useState((sug && !sug.collection_id ? sug.name : '') ?? '')
  const busy = actions.add.isPending || actions.create.isPending
  const ds = u.dataset
  const name = newName.trim() || ds.target
  const each = ds.sub_count ? ds.integration_s / ds.sub_count : 0
  return (
    <div className={s.ungrouped}>
      <div className={s.ungroupedName}>
        <ChooseBox checked={chosen} onChange={onChoose} label={`Select ${ds.target} · ${u.label}`} />
        <div>
          <Link to="/datasets/$id" params={{ id: String(ds.id) }} className={s.dsName}>
            {ds.target} · {u.label}
          </Link>
          <div className={v.muted}>
            {plural(u.sessions, 'session')} · {plural(ds.sub_count, 'sub')}
            {each && Number.isInteger(Math.round(each * 10) / 10)
              ? ` × ${exposureText(Math.round(each))}`
              : ''}
            {ds.first_utc
              ? ds.last_night && ds.last_night !== ds.first_utc.slice(0, 10)
                ? ` · ${nightText(ds.first_utc.slice(0, 10))} to ${nightText(ds.last_night)}`
                : ` · ${nightText(ds.first_utc.slice(0, 10))}`
              : ''}
          </div>
        </div>
      </div>
      <span className={s.figure}>{integrationText(ds.integration_s)}</span>
      <span className={v.note}>{sug?.collection_id ? sug.why : ''}</span>
      <form
        className={s.addTo}
        onSubmit={(e) => {
          e.preventDefault()
          if (choice === 'new') actions.create.mutate({ name, dataset_ids: [ds.id] })
          else actions.add.mutate({ id: Number(choice), dataset_ids: [ds.id] })
        }}
      >
        <Select
          size_="sm"
          value={choice}
          onChange={(e) => setChoice(e.target.value)}
          aria-label={`Add ${ds.target} · ${u.label} to`}
          options={[
            { value: 'new', label: '+ New collection' },
            ...collections.map((c) => ({
              value: c.id,
              label: c.id === sug?.collection_id ? `${c.name} (suggested)` : c.name,
            })),
          ]}
        />
        {choice === 'new' && (
          <Input
            size_="sm"
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
            placeholder={ds.target}
            aria-label="New collection name"
          />
        )}
        <Button type="submit" size="sm" disabled={busy}>
          {choice === 'new' ? 'Create' : 'Add'}
        </Button>
      </form>
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
      <span>{plural(n, 'item')} blocking grading.</span>
      <Link to="/reconcile" className={buttonClass({ size: 'sm' })}>
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
            <span key={l.id} className="mono">
              {l.mount_path}{' '}
            </span>
          ))}
      </p>
      <p>New FITS and XISF files appear here.</p>
      <div className={v.actions}>
        <Link to="/settings" hash="folders" className={buttonClass()}>
          Change watched folders
        </Link>
        <Link to="/settings" hash="patterns" className={buttonClass()}>
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
      <Input
        value={name}
        onChange={(e) => setName(e.target.value)}
        onKeyDown={(e) => e.key === 'Escape' && setName(null)}
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
  // kept + rejected is every graded sub: counted from the rate, each rounded on its own could make 101%
  const kept = d.success_rate != null ? Math.round(d.success_rate * d.graded) : 0
  const rejected = d.graded - kept
  const filterRows = sortFilters(Object.keys(d.by_filter).filter((f) => f !== '?'))
  const most = Math.max(1e-9, ...Object.values(d.by_filter))
  const rigMost = Math.max(1e-9, ...Object.values(d.by_rig))
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
        meta={plural(d.frames, 'sub')}
      >
        <div className={s.statsBody}>
          <StatGrid label="Totals">
            <StatTile
              label={filtered ? 'Subs in the filters' : 'Subs'}
              value={countText(d.frames)}
              detail={plural(d.nights, 'night')}
            />
            <StatTile
              label="Hours taken"
              value={integrationText(d.hours * 3600)}
              detail={`${integrationText(d.accepted_hours * 3600)} kept`}
            />
            <StatTile
              label="Kept"
              value={pct(d.success_rate)}
              detail={
                d.graded
                  ? `${countText(kept)} kept, ${countText(rejected)} rejected of ${countText(d.graded)} graded`
                  : 'nothing graded yet'
              }
            >
              {d.graded > 0 && <GradeMeter kept={kept} rejected={rejected} />}
            </StatTile>
            <StatTile
              label="Average SQM"
              value={d.avg_sqm != null ? numText(d.avg_sqm, 2) : '—'}
              unit={d.avg_sqm != null ? 'mag/″²' : undefined}
              detail={d.sqm_subs ? `from ${plural(d.sqm_subs, 'sub')}` : 'not recorded'}
            />
          </StatGrid>
          <div className={s.statGrid}>
            <div className={s.statBars} role="group" aria-label="Hours per filter">
              <span className={v.sectionLabel}>Hours per filter</span>
              {filterRows.map((f) => (
                <FilterMeter
                  key={f}
                  filter={f}
                  kept={d.by_filter[f] * 3600}
                  max={most * 3600}
                  value={integrationText(d.by_filter[f] * 3600)}
                  detail={`${integrationText(d.by_filter[f] * 3600)} taken`}
                />
              ))}
            </div>
            <div className={s.statBars} role="group" aria-label="Hours per rig">
              <span className={v.sectionLabel}>Hours per rig</span>
              {Object.entries(d.by_rig).map(([k, h]) => (
                <BarMeter key={k} label={k} value={h} max={rigMost} figure={integrationText(h * 3600)} />
              ))}
            </div>
          </div>
        </div>
      </Collapsible>
    </section>
  )
}

/** The four tiles under the totals: what needs you, missing calibration, what's ready to stack, this month. */
function Readouts({ r, scoped }: { r: Readouts; scoped: boolean }) {
  const needs = r.needs_you ?? { review: 0, reconcile: 0, stale: 0 }
  const needsTotal = needs.review + needs.reconcile + needs.stale
  const missing = r.missing_calibration ?? { subs: 0, top: [] }
  const ready = r.ready_to_stack ?? { datasets: 0, top: [] }
  const month = r.this_month ?? { hours: 0, nights: 0, last: { hours: 0, nights: 0 } }
  const needsParts = [
    needs.review ? `${plural(needs.review, 'sub')} to review` : '',
    needs.reconcile ? `${countText(needs.reconcile)} to reconcile` : '',
    needs.stale ? `${plural(needs.stale, 'stack')} out of date` : '',
  ].filter(Boolean)
  return (
    <section className={s.readouts} aria-labelledby="readouts-h">
      <div className={s.readoutsHead}>
        <h2 id="readouts-h" className={v.sectionLabel}>
          {scoped ? 'Whole library, not the filters' : 'Whole library'}
        </h2>
        <Help topic="These figures">
          Needs you, Missing calibration, Ready to stack and This month count everything in the library. The
          filters above narrow the totals and the collections, not these.
        </Help>
      </div>
      <StatGrid>
        <Link to={needs.review ? '/review' : needs.reconcile ? '/reconcile' : '/'} className={s.tileLink}>
          <StatTile
            label="Needs you"
            value={countText(needsTotal)}
            detail={needsTotal ? needsParts.join(' · ') : 'nothing waiting'}
          />
        </Link>
        <Link to="/calibration" className={s.tileLink}>
          <StatTile
            label="Missing calibration"
            value={countText(missing.subs)}
            detail={
              missing.subs
                ? [
                    'subs waiting',
                    ...missing.top.slice(0, 2).map((m) => `${m.reason} (${countText(m.subs)})`),
                  ].join(' · ')
                : 'every sub has its calibration'
            }
          />
        </Link>
        <StatTile
          label="Ready to stack"
          value={countText(ready.datasets)}
          detail={
            ready.top.length ? (
              <>
                {plural(ready.datasets, 'dataset')} {ready.datasets === 1 ? 'has' : 'have'} new subs:{' '}
                {ready.top.slice(0, 2).map((x, i) => (
                  <span key={x.id}>
                    {i > 0 && ' · '}
                    <Link to="/datasets/$id" params={{ id: String(x.id) }} className={s.quietLink}>
                      {x.name}
                    </Link>{' '}
                    (+{countText(x.new)})
                  </span>
                ))}
                {ready.datasets > 2 && ` · ${countText(ready.datasets - 2)} more`}
              </>
            ) : (
              'nothing new since the last stacks'
            )
          }
        />
        <StatTile
          label="This month"
          value={integrationText(month.hours * 3600)}
          detail={`${plural(month.nights, 'night')} · last month ${integrationText(month.last.hours * 3600)} over ${plural(month.last.nights, 'night')}`}
        />
      </StatGrid>
    </section>
  )
}
