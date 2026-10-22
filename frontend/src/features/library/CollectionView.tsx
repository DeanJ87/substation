// Collection (spec 006; design v2 L2): one object across rigs and years. Integration by rig and filter, a
// sessions timeline per rig, and the datasets.
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { getRouteApi, Link, useNavigate } from '@tanstack/react-router'
import { useEffect, useMemo, useState } from 'react'
import { api, unwrap } from '../../api/client'
import { optimistic, patchItems } from '../../api/optimistic'
import type { components } from '../../api/schema'
import {
  Button,
  buttonClass,
  Chip,
  ConfirmButton,
  EmptyState,
  ErrorState,
  Field,
  FilterTag,
  GradeMeter,
  Input,
  PageLoading,
  Select,
} from '../../components/ui'
import { Help } from '../../components/Help'
import { Modal } from '../../components/Modal'
import { compareFilters, filterName, sortFilters } from '../../components/filters'
import { toast } from '../../components/Toasts'
import { VerdictBadge } from '../../components/VerdictBadge'
import {
  angleText,
  binText,
  countText,
  dateText,
  datasetLabel,
  integrationText,
  monthText,
  nightShort,
  nightText,
  numText,
  pctText,
  plural,
} from '../format'
import { FilePath } from '../../components/FilePath'
import { stackPreviewUrl, useCollection, useCollectionActions, useLiveRefresh } from '../v2/hooks'
import v from '../v2/v2.module.css'
import s from './library.module.css'
import { collectionFacts, nameParts } from './names'
import c from './collection.module.css'
import { useDeleteCombined, useProjects } from './Projects'
import { FILE_DELETED } from '../changes/putAway'
import { useSort } from '../../components/sortable'
import { CloseLook, type LookMode, type LookTarget, Zoomable } from '../../components/CloseLook'
import { Collapsible } from '../../components/Collapsible'
import { LoadMore } from '../../components/LoadMore'
import { useProgressive } from '../../components/useProgressive'
import { TargetSky } from '../sky/SkyNights'
import tb from './tables.module.css'
import { usePlaceName } from '../map/place'
import { ProjectCards } from './ProjectCards'
import { inNights, omit, readScope, scopeQuery } from '../scope/scope'
import { ChooseBox, useChosen } from '../../components/BulkBar'
import { DatasetBulkBar } from './DatasetBulkBar'
import { CollectionFiles } from './CollectionFiles'
import { CollectionMenu, type PutAwayStep } from './CollectionMenu'

const route = getRouteApi('/app/collections/$id')

export function CollectionView() {
  useLiveRefresh()
  const { id } = route.useParams()
  const q = useCollection(Number(id))
  const navigate = useNavigate()
  const [editing, setEditing] = useState(false)
  const [adding, setAdding] = useState(false)
  const [putAway, setPutAway] = useState<PutAwayStep>(null)
  const [range, setRange] = useState<[string, string] | null>(null)
  const [project, setProject] = useState<number | null>(null)
  const projects = useProjects(Number(id))
  const search = route.useSearch()
  const tab = search.tab ?? 'overview'
  const setTab = (t: string) =>
    void navigate({
      to: '.',
      search: { ...search, tab: t === 'overview' ? undefined : (t as 'datasets') },
      replace: true,
    })
  // from the map: only the nights shot at one place (spec 012)
  const only = useMemo(() => (search.nights ? new Set(search.nights.split(',')) : null), [search.nights])
  // the Library's or the map's filters (spec 018): this page narrows its sessions to their nights, and its
  // links (the Library, the map, a night) carry them on
  const scope = readScope(search)
  const carry = scopeQuery(omit(scope, 'collection'))
  const nightsScoped = !!(scope.date || scope.date_from || scope.date_to)
  const [atLat, atLon] = (search.at ?? '').split(',').map(Number)
  const atName = usePlaceName(search.at ? atLat : null, search.at ? atLon : null)
  const qc = useQueryClient()
  type Card = { id: number; name: string }
  const renameCol = useMutation({
    mutationFn: async (name: string) =>
      unwrap(await api.PATCH('/collections/{id}', { params: { path: { id: Number(id) } }, body: { name } })),
    scope: { id: `collection-${id}` },
    meta: { failed: "Couldn't rename the collection" },
    ...optimistic(qc, (name: string) => [
      [
        ['collection', Number(id)],
        (o) => o && { ...(o as object), card: { ...(o as { card: Card }).card, name } },
      ],
      [
        ['library'],
        (o) =>
          o && {
            ...(o as object),
            collections: patchItems<Card>(
              (o as { collections: Card[] }).collections,
              (x) => x.id === Number(id),
              (x) => ({ ...x, name }),
            ),
          },
      ],
    ]),
  })
  const d = q.data
  const filters = useMemo(() => {
    const all = new Set<string>()
    for (const row of Object.values(d?.matrix ?? {})) for (const f of Object.keys(row)) all.add(f)
    return sortFilters([...all])
  }, [d])
  if (q.isError)
    return (
      <ErrorState title="Couldn't load the collection" onRetry={() => q.refetch()}>
        {q.error.message}
      </ErrorState>
    )
  if (!d) return <PageLoading />
  const card = d.card
  // a master to combine from: current or stale (failed and superseded ones don't count)
  const usable = d.masters.some((m) => m.state === 'current' || m.state === 'stale')
  const chosenProject = projects.data?.projects.find((p) => p.id === project)
  const inProject = (dsId: number) => !chosenProject || chosenProject.dataset_ids.includes(dsId)
  const rigs = Object.keys(d.matrix).sort()
  // the rig with the most accepted integration sets the framing others are registered to (006-DR-08)
  const total = (r: string) => Object.values(d.matrix[r]).reduce((x, y) => x + y, 0)
  const reference = rigs.length > 1 ? rigs.reduce((a, b) => (total(b) > total(a) ? b : a)) : null
  const totals = Object.fromEntries(
    filters.map((f) => [f, rigs.reduce((n, r) => n + (d.matrix[r][f] ?? 0), 0)]),
  )

  return (
    <div className={v.page}>
      <header className={v.head}>
        <div>
          <div className={v.crumbs}>
            <Link to="/" search={carry}>
              Library
            </Link>{' '}
            / Collections
          </div>
          <h1>
            {nameParts(card.name).title}
            {nameParts(card.name).designation && (
              <span className={s.designation}>{nameParts(card.name).designation}</span>
            )}
          </h1>
          <div className={v.sub}>
            {collectionFacts(card)} · {plural(card.rigs.length, 'rig')} · {plural(card.sessions, 'session')}
            {card.first_night && ` from ${nightText(card.first_night)} to ${nightText(card.last_night)}`}
          </div>
        </div>
        {/* one primary; archiving and deleting live in the ⋯ menu, away from Add (C17, 006-DR-40) */}
        <div className={v.actions}>
          <Link to="/map" search={{ ...carry, collection: card.id }} className={buttonClass()}>
            Map
          </Link>
          <Button onClick={() => setEditing(true)}>Edit collection</Button>
          <Button variant="primary" onClick={() => setAdding(true)}>
            Add datasets
          </Button>
          <CollectionMenu
            id={card.id}
            name={card.name}
            onMasters={() => setTab('masters')}
            open={putAway}
            setOpen={setPutAway}
          />
        </div>
      </header>

      {adding && (
        <AddDatasets id={card.id} onClose={() => setAdding(false)} onDone={() => void q.refetch()} />
      )}
      {editing && (
        <EditCollection
          name={card.name}
          onClose={() => setEditing(false)}
          onRename={(name) => name !== card.name && renameCol.mutate(name)}
        />
      )}

      {chosenProject && (
        <p className={c.scoped} role="status">
          Showing only <strong>{chosenProject.name}</strong>
          <Button size="sm" onClick={() => setProject(null)}>
            Show everything
          </Button>
        </p>
      )}

      <div className={v.tabs} role="tablist" aria-label="Collection">
        {(
          [
            ['overview', 'Overview'],
            ['datasets', `Datasets ${d.datasets.length}`],
            ['sessions', `Sessions ${card.sessions}`],
            ['masters', `Masters ${d.masters.length}`],
            ['sky', 'Sky'],
          ] as const
        ).map(([t, label]) => (
          <button key={t} role="tab" aria-selected={tab === t} className={v.tab} onClick={() => setTab(t)}>
            {label}
          </button>
        ))}
      </div>

      {tab === 'overview' && (
        <>
          <ProjectCards
            collectionId={card.id}
            datasets={d.datasets}
            value={project}
            onChange={setProject}
            onArchive={() => setPutAway('archive')}
            onMasters={() => setTab('masters')}
          />
          <Framing key={project ?? 'all'} id={card.id} project={project} />
          <div className={c.grid}>
            <section className={`${v.card} ${tb.flush}`}>
              <Collapsible
                id="collection-matrix"
                title="Kept integration by rig and filter"
                meta={`${plural(rigs.length, 'rig')} · ${plural(filters.length, 'filter')}`}
              >
                <table className={`${v.table} ${tb.table} cards`}>
                  <thead>
                    <tr>
                      <th>Rig</th>
                      {filters.map((f) => (
                        <th key={f} className={tb.num}>
                          <FilterTag filter={f} plain />
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {rigs.map((r) => {
                      const rd = d.rig_details.find((x) => x.name === r)
                      return (
                        <tr key={r}>
                          <td>
                            {/* renaming and merging rigs live in Settings › Rigs only (C19) */}
                            <Link
                              to="/settings"
                              hash="rigs"
                              className={c.rigLink}
                              title="Rename or merge in Settings › Rigs"
                            >
                              {r}
                            </Link>
                            {rd && (
                              <div className={v.muted}>
                                {[
                                  r === reference ? 'reference' : '',
                                  rd.camera,
                                  rd.focal_mm ? `${rd.focal_mm} mm` : '',
                                  rd.image_scale ? `${numText(rd.image_scale, 2)}″/px` : '',
                                ]
                                  .filter(Boolean)
                                  .join(' · ')}
                              </div>
                            )}
                          </td>
                          {filters.map((f) => (
                            <td key={f} className={tb.num} data-label={filterName(f)}>
                              {d.matrix[r][f] ? integrationText(d.matrix[r][f]) : '—'}
                            </td>
                          ))}
                        </tr>
                      )
                    })}
                    <tr>
                      <td>
                        <strong>Total</strong>
                        <div className={v.muted}>{integrationText(card.accepted_integration_s)} kept</div>
                      </td>
                      {filters.map((f) => (
                        <td key={f} className={`${tb.num} ${c.total}`} data-label={filterName(f)}>
                          {integrationText(totals[f])}
                        </td>
                      ))}
                    </tr>
                  </tbody>
                </table>
              </Collapsible>
            </section>
            <MergeNames
              id={card.id}
              datasets={d.datasets.map((x) => x.dataset)}
              onDone={() => void q.refetch()}
            />
          </div>

          <CollectionFiles id={card.id} name={card.name} />

          <DatasetTable resetKey={project} rows={d.datasets.filter((x) => inProject(x.dataset.id))} />
        </>
      )}
      {tab === 'datasets' && (
        <DatasetTable
          resetKey={project}
          rows={d.datasets.filter((x) => inProject(x.dataset.id))}
          collectionId={card.id}
        />
      )}
      {tab === 'sessions' && (
        <>
          <section className={`${v.card} ${v.cardPad}`}>
            <Collapsible
              id="collection-sessions"
              title="Sessions"
              meta={`${plural(card.sessions, 'session')} · kept integration per night`}
            >
              <Timeline sessions={d.sessions} rigs={rigs} range={range} onRange={setRange} />
            </Collapsible>
          </section>

          {only && (
            <div className={`${v.card} ${v.cardPad} ${v.actions}`} role="status">
              <span>
                Showing the {only.size} night{only.size === 1 ? '' : 's'} shot
                {search.at ? ` at ${atName.data ?? 'this place'}` : ' at one place'}.
              </span>
              <Link to="." search={{ ...carry, tab: 'sessions' }} className={buttonClass({ size: 'sm' })}>
                Show every session
              </Link>
            </div>
          )}
          {!only && nightsScoped && (
            <div className={`${v.card} ${v.cardPad} ${v.actions}`} role="status">
              <span>Showing the sessions in the nights the Library was filtered to.</span>
              <Link
                to="."
                search={{ ...scopeQuery(omit(scope, 'date', 'date_from', 'date_to')), tab: 'sessions' }}
                className={buttonClass({ size: 'sm' })}
              >
                Show every session
              </Link>
            </div>
          )}
          <SessionList
            sessions={d.sessions.filter(
              (x) =>
                (only ? only.has(x.night) : inNights(scope, x.night)) &&
                (!range || (x.night >= range[0] && x.night <= range[1])),
            )}
            carry={carry}
          />
        </>
      )}
      {tab === 'sky' && (
        // every frame of the target on the sky, coloured by filter, with Play through all its nights (2026-10-16)
        <section className={`${v.card} ${v.cardPad}`}>
          <TargetSky
            kind="collection"
            id={card.id}
            nights={{ date: scope.date, date_from: scope.date_from, date_to: scope.date_to }}
          />
        </section>
      )}

      {tab === 'masters' && !usable && (
        // one empty state, not one per project (C21): combined masters need each dataset's master first
        <EmptyState
          title="No masters yet"
          action={
            <Button onClick={() => setTab('datasets')} title="Stack each dataset from its page">
              Open the datasets
            </Button>
          }
        >
          Stack each dataset first; combined masters are made from those.
        </EmptyState>
      )}
      {tab === 'masters' && !usable && <MasterList masters={d.masters} />}
      {tab === 'masters' && usable && (
        <>
          {project === null && projects.data?.projects.length ? (
            // all datasets: each project's own combined masters (they're never combined across projects)
            projects.data.projects.map((p) => (
              <Combined key={p.id} id={card.id} project={p.id} projectName={p.name} />
            ))
          ) : (
            <Combined id={card.id} project={project} projectName={chosenProject?.name ?? null} />
          )}
          <MasterList masters={d.masters} />
        </>
      )}
    </div>
  )
}

/** A rig's name, renamed in place ("Askar 71F + A7 III"); merging lives in Settings → Rigs. */
type ColDataset = NonNullable<ReturnType<typeof useCollection>['data']>['datasets'][number]
type ColMaster = NonNullable<ReturnType<typeof useCollection>['data']>['masters'][number]
type ColSession = NonNullable<ReturnType<typeof useCollection>['data']>['sessions'][number]

const shortDate = (iso: string) => dateText(`${iso.slice(0, 10)}T12:00:00`)

/** The collection's datasets (006-DR-06): state as a badge, grades as a split bar, last night as a short date. */
function DatasetTable({
  rows: all,
  resetKey,
  collectionId,
}: {
  rows: ColDataset[]
  resetKey: unknown
  collectionId?: number // given on the Datasets tab: rows can be chosen and acted on together (spec 016 U6)
}) {
  const navigate = useNavigate()
  const pick = useChosen<number>()
  const choosing = collectionId !== undefined
  const allIds = all.map((x) => x.dataset.id)
  const picked = allIds.filter((i) => pick.chosen.has(i)).length
  const kept = (x: ColDataset) => {
    const t = x.dataset.accepted_count + x.dataset.down_count + x.dataset.rejected_count
    return t ? (x.dataset.accepted_count + x.dataset.down_count) / t : null
  }
  const { sorted, th, sort } = useSort(all, {
    name: (x) => x.label,
    state: (x) => x.dataset.state,
    sessions: (x) => x.sessions,
    accepted: (x) => x.dataset.accepted_integration_s,
    grades: kept,
    last: (x) => x.last_night,
  })
  // sorted first, then sliced; a new sort or filter starts again from the top
  const { visible, hasMore, more } = useProgressive(sorted, 60, `${resetKey}|${sort?.key}|${sort?.desc}`)
  return (
    <section className={`${v.card} ${tb.flush}`}>
      <Collapsible id="collection-datasets" title="Datasets" meta={countText(all.length)}>
        {choosing && (
          <DatasetBulkBar
            chosen={pick.chosen}
            onClear={pick.clear}
            shown={all.length}
            onChooseShown={() => pick.setAll(allIds, true)}
            from={collectionId}
          />
        )}
        <div className={tb.pane}>
          <table className={`${v.table} ${tb.table} cards`}>
            <thead>
              <tr>
                {choosing && (
                  <th className={c.chooseCell}>
                    <ChooseBox
                      checked={picked > 0 && picked === all.length}
                      mixed={picked > 0 && picked < all.length}
                      onChange={(on) => pick.setAll(allIds, on)}
                      label="Select every dataset"
                    />
                  </th>
                )}
                {th('name', 'Dataset')}
                {th('state', 'State')}
                {th('sessions', 'Sessions', tb.num)}
                {th('accepted', 'Kept', tb.num)}
                {th('grades', 'Grades')}
                {th('last', 'Last night', tb.num)}
              </tr>
            </thead>
            <tbody>
              {visible.map((x) => {
                const ds = x.dataset
                const tot = ds.accepted_count + ds.down_count + ds.rejected_count
                return (
                  <tr
                    key={ds.id}
                    className={v.rowLink}
                    onClick={() => void navigate({ to: '/datasets/$id', params: { id: String(ds.id) } })}
                    aria-selected={choosing ? pick.chosen.has(ds.id) : undefined}
                  >
                    {choosing && (
                      <td className={c.chooseCell} data-label="">
                        <ChooseBox
                          checked={pick.chosen.has(ds.id)}
                          onChange={() => pick.toggle(ds.id)}
                          label={`Select ${x.label}`}
                        />
                      </td>
                    )}
                    <td>
                      {/* target · panel · filter, the rig as secondary text (C08) */}
                      <Link to="/datasets/$id" params={{ id: String(ds.id) }} className={s.dsName}>
                        {datasetLabel(ds)}
                      </Link>
                      <div className={v.muted}>
                        {[
                          x.rig ?? ds.rig,
                          ds.gain != null ? `gain ${ds.gain}` : '',
                          ds.binning ? binText(ds.binning) : '',
                        ]
                          .filter(Boolean)
                          .join(' · ')}
                      </div>
                    </td>
                    <td data-label="State" data-wide>
                      <DatasetState x={x} />
                    </td>
                    <td className={tb.num} data-label="Sessions">
                      {x.sessions}
                    </td>
                    <td className={tb.num} data-label="Kept">
                      {integrationText(ds.accepted_integration_s)}
                    </td>
                    <td data-label="Grades" data-wide>
                      {tot ? (
                        <div className={c.grades}>
                          <GradeMeter
                            kept={ds.accepted_count}
                            down={ds.down_count}
                            rejected={ds.rejected_count}
                          />
                          <span>
                            {countText(ds.accepted_count + ds.down_count)} of {countText(tot)} kept
                          </span>
                        </div>
                      ) : (
                        '—'
                      )}
                    </td>
                    <td className={`${v.muted} ${tb.num}`} data-label="Last night">
                      {x.last_night ? nightText(x.last_night) : '—'}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
          <LoadMore hasMore={hasMore} loading={false} onMore={more} />
        </div>
      </Collapsible>
    </section>
  )
}

function DatasetState({ x }: { x: ColDataset }) {
  const ds = x.dataset
  if (ds.state === 'awaiting_calibration') return <VerdictBadge state="await" label="Awaiting calibration" />
  if (ds.state === 'needs_reconciliation') return <VerdictBadge state="recon" label="Needs reconciliation" />
  if (x.master_state === 'running' || x.master_state === 'queued')
    return (
      <VerdictBadge
        state="integ"
        label={`Integrating v${x.master_version}${x.master_progress ? ` · ${Math.round(x.master_progress * 100)}%` : ''}`}
      />
    )
  if (x.master_state === 'stale') return <VerdictBadge state="stale" label="Master stale" />
  if (x.master_state === 'failed')
    return <VerdictBadge state="reject" label={`Master v${x.master_version} failed`} />
  if (x.master_state === 'current')
    return (
      <span className={v.muted}>
        Master current{x.master_finished ? ` · ${nightShort(x.master_finished.slice(0, 10))}` : ''}
      </span>
    )
  return <span className={v.muted}>No master yet</span>
}

function SessionList({
  sessions,
  carry,
}: {
  sessions: ColSession[]
  carry: Record<string, string | number>
}) {
  const newest = useMemo(() => [...sessions].reverse(), [sessions])
  const { visible, hasMore, more } = useProgressive(newest, 60)
  return (
    <section className={`${v.card} ${tb.flush}`}>
      <Collapsible id="collection-nights" title="Every session" meta={countText(sessions.length)}>
        <div className={tb.pane}>
          <table className={`${v.table} ${tb.table} cards`}>
            <thead>
              <tr>
                <th>Night</th>
                <th>Rig</th>
                <th>Filters</th>
                <th className={tb.num}>Subs</th>
                <th className={tb.num}>Kept</th>
              </tr>
            </thead>
            <tbody>
              {visible.map((x) => (
                <tr key={`${x.night}-${x.rig}`}>
                  <td className={tb.nowrap}>
                    <Link
                      to="/nights/$date"
                      params={{ date: x.night }}
                      search={carry}
                      className={s.quietLink}
                    >
                      {nightText(x.night)}
                    </Link>
                  </td>
                  <td data-label="Rig">{x.rig}</td>
                  <td data-label="Filters">
                    <span className={c.filterList}>
                      {sortFilters(x.filters).map((f) => (
                        <FilterTag key={f} filter={f} plain />
                      ))}
                    </span>
                  </td>
                  <td className={tb.num} data-label="Subs">
                    {countText(x.subs)}
                  </td>
                  <td className={tb.num} data-label="Kept">
                    {integrationText(x.accepted_s)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <LoadMore hasMore={hasMore} loading={false} onMore={more} />
        </div>
      </Collapsible>
    </section>
  )
}

const MASTER_TAG: Record<string, string> = {
  current: 'Current',
  stale: 'Stale',
  superseded: 'Superseded',
  failed: 'Failed',
  cancelled: 'Cancelled',
  running: 'Integrating',
  queued: 'Waiting',
}

function MasterList({ masters }: { masters: ColMaster[] }) {
  // older versions are kept but out of the way: their images can look like another panel's (2026-10-11)
  const [old, setOld] = useState(false)
  const older = masters.filter(
    (m) => m.state === 'superseded' || m.state === 'failed' || m.state === 'cancelled',
  )
  const shown = old ? masters : masters.filter((m) => !older.includes(m))
  const { visible, hasMore, more } = useProgressive(shown, 24, old)
  if (!masters.length) return null
  return (
    <Collapsible id="collection-masters" title="Masters" meta={countText(shown.length)}>
      {older.length > 0 && (
        <div className={v.actions}>
          <Chip pressed={old} onClick={() => setOld(!old)} count={older.length}>
            Older or failed
          </Chip>
        </div>
      )}
      <div className={c.masters}>
        {visible.map((m) => (
          <Link
            key={m.id}
            to="/datasets/$id"
            params={{ id: String(m.dataset_id) }}
            search={{ tab: 'masters' }}
            className={`${v.card} ${c.masterCard}`}
          >
            <div className={c.masterThumb}>
              {m.has_preview && (
                <Zoomable target={{ kind: 'master', id: m.id }} name={`${m.dataset} v${m.version}`}>
                  <img src={stackPreviewUrl(m.id)} alt={`${m.dataset} v${m.version}`} loading="lazy" />
                </Zoomable>
              )}
            </div>
            <div className={c.masterBody}>
              <strong>
                {m.dataset} · v{m.version}
              </strong>
              <span className={v.muted}>
                {MASTER_TAG[m.state] ?? m.state} · {plural(m.sub_count, 'sub')} ·{' '}
                {integrationText(m.integration_s)}
                {m.finished_at ? ` · ${shortDate(m.finished_at)}` : ''}
              </span>
            </div>
          </Link>
        ))}
      </div>
      <LoadMore hasMore={hasMore} loading={false} onMore={more} />
    </Collapsible>
  )
}

/** Combined masters (004-DR-05, T022): one master per filter, each dataset's current master registered to the
 * reference framing and same-filter masters averaged, so the filters line up for colour combination. */
type CombinedPlan = components['schemas']['CombinedPlanOut']
function Combined({
  id,
  project,
  projectName,
}: {
  id: number
  project: number | null
  projectName: string | null
}) {
  const qc = useQueryClient()
  const q = useQuery({
    queryKey: ['combined', id, project],
    queryFn: async () =>
      unwrap(
        await api.GET('/collections/{id}/combined', {
          params: { path: { id }, query: project ? { project } : {} },
        }),
      ),
    refetchInterval: (query) =>
      query.state.data?.combined.some((x) => x.state === 'queued' || x.state === 'running') ? 3000 : false,
  })
  const start = useMutation({
    mutationFn: async () =>
      unwrap(
        await api.POST('/collections/{id}/combined', {
          params: { path: { id }, query: project ? { project } : {} },
        }),
      ),
    scope: { id: `combined-${id}-${project}` },
    meta: { failed: "Couldn't start the combined masters" },
    // a waiting version per filter at once, so the button flips to Combining… and the cards show Waiting
    ...optimistic(qc, () => [
      [
        ['combined', id, project],
        (o) => {
          const p = o as CombinedPlan | undefined
          if (!p) return o
          const queued = Object.entries(p.filters).map(([filter, inputs], i) => ({
            id: -1 - i,
            filter,
            inputs,
            version: Math.max(0, ...p.combined.filter((x) => x.filter === filter).map((x) => x.version)) + 1,
            state: 'queued',
            state_reason: '',
            stale: '',
            error: null,
            finished_at: null,
            has_preview: false,
            integration_s: inputs.reduce((n, x) => n + (x.integration_s ?? 0), 0),
          }))
          return { ...p, combined: [...queued, ...p.combined] }
        },
      ],
    ]),
  })
  const removeCombined = useDeleteCombined()
  const d = q.data
  if (!d) return null
  const filters = Object.entries(d.filters)
  const busy = d.combined.some((x) => x.state === 'queued' || x.state === 'running')
  return (
    <section className={`${v.card} ${v.cardPad}`}>
      <Collapsible
        id={`collection-combined-${project ?? 'all'}`}
        title={`Combined masters${projectName ? ` · ${projectName}` : ''}`}
        meta={
          <Button
            size="sm"
            disabled={!d.reference || busy || start.isPending}
            onClick={() => start.mutate()}
            title={d.reference ? undefined : 'Stack each dataset first'}
          >
            {busy ? 'Combining…' : 'Stack combined masters'}
          </Button>
        }
      >
        <p className={v.muted}>
          {d.reference
            ? `Aligned to ${d.reference_label}. ${filters
                .sort(([a], [b]) => compareFilters(a, b))
                .map(([f, inputs]) => `${filterName(f)}: ${plural(inputs.length, 'master')}`)
                .join(' · ')}`
            : 'Stack each dataset in this project first.'}
        </p>
        {d.left_out.length > 0 && (
          <p className={v.muted}>Left out (different pixel scale): {d.left_out.join('; ')}.</p>
        )}
        {d.combined.length > 0 && (
          <div className={c.masters}>
            {d.combined.map((m) => (
              <article key={m.id} className={`${v.card} ${c.masterCard}`}>
                <div className={c.masterThumb}>
                  {m.has_preview && (
                    <Zoomable
                      target={{ kind: 'combined', id: m.id }}
                      name={`${m.filter} combined v${m.version}`}
                    >
                      <img
                        src={`/api/v1/combined/${m.id}/preview?size=thumb`}
                        alt={`${m.filter} combined`}
                        loading="lazy"
                      />
                    </Zoomable>
                  )}
                </div>
                <div className={c.masterBody}>
                  <strong>
                    {filterName(m.filter)} · v{m.version}
                  </strong>
                  <span className={v.muted}>
                    {MASTER_TAG[m.state] ?? m.state} · {integrationText(m.integration_s)} from{' '}
                    {plural(m.inputs.length, 'master')}
                    {m.finished_at ? ` · ${shortDate(m.finished_at)}` : ''}
                  </span>
                  {m.stale && <span className={v.warn}>{m.stale}</span>}
                  {m.state_reason && <span className={v.muted}>{m.state_reason}</span>}
                  {m.error && <span className={v.bad}>{m.error}</span>}
                  {m.state === 'current' && (
                    <FilePath path={m.file_path ?? ''} download={`/api/v1/combined/${m.id}/download`} />
                  )}
                  {m.id > 0 && m.state !== 'queued' && m.state !== 'running' && (
                    <span>
                      <ConfirmButton
                        size="sm"
                        variant="ghost"
                        question={
                          <>
                            Delete {filterName(m.filter)} combined v{m.version}? {FILE_DELETED}
                          </>
                        }
                        confirm="Delete"
                        onConfirm={() =>
                          removeCombined.mutate({
                            id: m.id,
                            name: `${filterName(m.filter)} combined v${m.version}`,
                          })
                        }
                      >
                        Delete…
                      </ConfirmButton>
                    </span>
                  )}
                </div>
              </article>
            ))}
          </div>
        )}
      </Collapsible>
    </section>
  )
}

/** Add datasets (006-DR-05): candidates nearest in pointing first, each with why; several at once. A dialog, so
 * the page doesn't shift and Escape or Cancel closes it (C36). */
function AddDatasets({ id, onClose, onDone }: { id: number; onClose: () => void; onDone: () => void }) {
  const q = useQuery({
    queryKey: ['candidates', id],
    queryFn: async () => unwrap(await api.GET('/collections/{id}/candidates', { params: { path: { id } } })),
  })
  const actions = useCollectionActions()
  const [picked, setPicked] = useState<number[]>([])
  const rows = q.data ?? []
  return (
    <Modal label="Add datasets" onClose={onClose} size="md">
      <div className={c.dialog}>
        <h2 className={c.dialogTitle}>
          Add datasets
          <Help topic="Add datasets">
            Datasets pointing near this collection, or with a matching object name, nearest first.
          </Help>
        </h2>
        {q.isPending && <p className={v.muted}>Searching…</p>}
        {q.isSuccess && rows.length === 0 && (
          <EmptyState inline>No datasets point near it or share its name.</EmptyState>
        )}
        <ul className={c.candidates}>
          {rows.map((r) => (
            <li key={r.dataset_id}>
              <label>
                <input
                  type="checkbox"
                  checked={picked.includes(r.dataset_id)}
                  onChange={(e) =>
                    setPicked(
                      e.target.checked ? [...picked, r.dataset_id] : picked.filter((x) => x !== r.dataset_id),
                    )
                  }
                />
                <span>
                  <strong>
                    {r.target} · {r.label}
                  </strong>{' '}
                  <span className={v.muted}>
                    {plural(r.subs, 'sub')} · {integrationText(r.integration_s)}
                    {r.in_collection ? ` · in ${r.in_collection}` : ''}
                  </span>
                  <span className={`${v.note} ${c.candNote}`}>{r.note}</span>
                </span>
              </label>
            </li>
          ))}
        </ul>
        <div className={v.actions}>
          <Button
            variant="primary"
            disabled={!picked.length || actions.add.isPending}
            onClick={() => {
              actions.add.mutate({ id, dataset_ids: picked }, { onSettled: onDone })
              onClose()
            }}
          >
            Add {picked.length || ''} dataset{picked.length === 1 ? '' : 's'}
          </Button>
          <Button onClick={onClose}>Cancel</Button>
        </div>
      </div>
    </Modal>
  )
}

/** Edit collection (C36): its name, in a dialog with Cancel and Escape. Delete is in the ⋯ menu (006-DR-40). */
function EditCollection({
  name,
  onClose,
  onRename,
}: {
  name: string
  onClose: () => void
  onRename: (name: string) => void
}) {
  const [text, setText] = useState(name)
  return (
    <Modal label="Edit collection" onClose={onClose} size="sm">
      <form
        className={c.dialog}
        onSubmit={(e) => {
          e.preventDefault()
          if (text.trim()) onRename(text.trim())
          onClose()
        }}
      >
        <h2 className={c.dialogTitle}>Edit collection</h2>
        <Field label="Name">
          <Input value={text} onChange={(e) => setText(e.target.value)} />
        </Field>
        <div className={v.actions}>
          <Button type="submit" variant="primary" disabled={!text.trim()}>
            Save
          </Button>
          <Button onClick={onClose}>Cancel</Button>
        </div>
      </form>
    </Modal>
  )
}

/** Framing (006-DR-09, -21, -22): every dataset's solved field, north up and east left, with each one's sub image
 * placed by its plate solve. Select rows like a file list (click, Shift, Cmd/Ctrl, drag, All/None), filter by
 * filter, or view HOO/SHO palettes made from single subs; outlines can be hidden. */
type FramingRow = NonNullable<ReturnType<typeof useFraming>['data']>[number]
const PALETTES: Record<string, { label: string; map: Record<string, ('r' | 'g' | 'b')[]> }> = {
  hoo: { label: 'HOO', map: { Hα: ['r'], OIII: ['g', 'b'] } },
  sho: { label: 'SHO', map: { SII: ['r'], Hα: ['g'], OIII: ['b'] } },
}

function useFraming(id: number, reference: number | null, project: number | null = null) {
  return useQuery({
    queryKey: ['framing', id, reference, project],
    queryFn: async () =>
      unwrap(
        await api.GET('/collections/{id}/framing', {
          params: {
            path: { id },
            query: { ...(reference ? { reference } : {}), ...(project ? { project } : {}) },
          },
        }),
      ),
    placeholderData: (prev) => prev,
  })
}

function Framing({ id, project }: { id: number; project: number | null }) {
  const [reference, setReference] = useState<number | null>(null)
  const [selected, setSelected] = useState<Set<number> | null>(null)
  const [anchor, setAnchor] = useState<number | null>(null)
  const [dragging, setDragging] = useState(false)
  const [outlines, setOutlines] = useState(true)
  const [filter, setFilter] = useState<string>('all')
  const [palette, setPalette] = useState<string | null>(null)
  const [look, setLook] = useState<{ target: LookTarget; name: string } | null>(null)
  const [lookMode, setLookMode] = useState<LookMode>('full')
  const q = useFraming(id, reference, project)
  const all = q.data ?? []
  const visible = filter === 'all' ? all : all.filter((r) => r.filter === filter)
  const { sorted: tableRows, th: fth } = useSort(visible, {
    name: (r) => r.label,
    field: (r) => r.fov_w * r.fov_h,
    scale: (r) => r.scale,
    offset: (r) => (r.reference ? -1 : r.offset_arcmin),
    overlap: (r) => r.overlap,
  })
  useEffect(() => {
    const up = () => setDragging(false)
    window.addEventListener('mouseup', up)
    return () => window.removeEventListener('mouseup', up)
  }, [])
  if (!all.length) return null
  const filters = [...new Set(all.map((r) => r.filter).filter((f): f is string => !!f))]
  const palettes = Object.entries(PALETTES).filter(([, p]) =>
    Object.keys(p.map).every((f) => filters.includes(f)),
  )
  const rows = filter === 'all' ? all : all.filter((r) => r.filter === filter)
  const mosaic = new Set(all.map((r) => r.panel).filter((p) => p != null)).size > 1
  const ref = all.find((r) => r.reference) ?? all[0]
  const chosen = selected ?? new Set(mosaic ? rows.map((r) => r.dataset_id) : [ref.dataset_id])
  const pal = palette ? PALETTES[palette] : null
  // stacks drawn over single subs (owner 2026-10-13: a noisy sub covered a clean 12-hour master)
  const imaged = (pal ? all.filter((r) => r.filter && pal.map[r.filter]) : rows)
    .filter((r) => chosen.has(r.dataset_id) && (r.image_url || r.image) && r.image_corners.length === 4)
    .sort((a, b) => Number(a.image_kind === 'master') - Number(b.image_kind === 'master'))
  const pick = (r: FramingRow, e: { shiftKey: boolean; metaKey: boolean; ctrlKey: boolean }) => {
    const ids = rows.map((x) => x.dataset_id)
    const next = new Set(chosen)
    if (e.shiftKey && anchor != null) {
      const [i, j] = [ids.indexOf(anchor), ids.indexOf(r.dataset_id)].sort((x, y) => x - y)
      ids.slice(i, j + 1).forEach((x) => next.add(x))
    } else if (e.metaKey || e.ctrlKey) {
      if (next.has(r.dataset_id)) next.delete(r.dataset_id)
      else next.add(r.dataset_id)
      setAnchor(r.dataset_id)
    } else {
      next.clear()
      next.add(r.dataset_id)
      setAnchor(r.dataset_id)
    }
    setSelected(next)
  }
  // drawing coordinates: x is west (east is left on the sky), y is south (SVG y grows downwards)
  const pts = all.flatMap((r) => [...r.corners, ...r.image_corners])
  const xs = pts.map((p) => -p[0])
  const ys = pts.map((p) => -p[1])
  const span = Math.max(Math.max(...xs) - Math.min(...xs), Math.max(...ys) - Math.min(...ys))
  const pad = span * 0.06
  const [x0, x1, y0, y1] = [
    Math.min(...xs) - pad,
    Math.max(...xs) + pad,
    Math.min(...ys) - pad,
    Math.max(...ys) + pad,
  ]
  const deg = (n: number) => angleText(n, 2)
  const short = (label: string) =>
    label
      .split(' · ')
      .slice(1)
      .join(' · ')
      .replace(/Panel (\d+)/, 'P$1') || label
  const centre = (x: FramingRow) => [
    x.corners.reduce((a, p) => a + p[0], 0) / 4,
    x.corners.reduce((a, p) => a + p[1], 0) / 4,
  ]
  const shown = rows.filter((r) => chosen.has(r.dataset_id))
  return (
    <section className={`${v.card} ${v.cardPad}`}>
      <Collapsible
        id="collection-framing"
        title="Framing"
        meta={
          <Field inline label="Reference" className={c.framingPick}>
            <Select
              size_="sm"
              value={ref.dataset_id}
              onChange={(e) => setReference(Number(e.target.value))}
              options={all.map((r) => ({ value: r.dataset_id, label: r.label }))}
            />
          </Field>
        }
      >
        <div className={`${v.pills} ${c.framingBar}`} role="group" aria-label="Filter and palette">
          <Chip pressed={filter === 'all' && !palette} onClick={() => (setFilter('all'), setPalette(null))}>
            All filters
          </Chip>
          {sortFilters(filters).map((f) => (
            <Chip
              key={f}
              pressed={filter === f}
              onClick={() => {
                setFilter(f)
                setSelected(new Set(all.filter((r) => r.filter === f).map((r) => r.dataset_id)))
              }}
            >
              <FilterTag filter={f} plain />
            </Chip>
          ))}
          <span className={c.framingSep} aria-hidden="true" />
          <Button
            size="sm"
            variant="ghost"
            onClick={() => setSelected(new Set(rows.map((r) => r.dataset_id)))}
          >
            All
          </Button>
          <Button size="sm" variant="ghost" onClick={() => setSelected(new Set())}>
            None
          </Button>
          <Chip pressed={outlines} onClick={() => setOutlines(!outlines)}>
            Outlines
          </Chip>
        </div>
        <div className={`${v.pills} ${c.framingBar}`} role="group" aria-label="Colour">
          <span className={v.muted}>Colour</span>
          <Chip pressed={!palette} onClick={() => setPalette(null)}>
            As shot
          </Chip>
          {palettes.map(([k, p]) => (
            <Chip
              key={k}
              pressed={palette === k}
              title={`${Object.entries(p.map)
                .map(([f, ch]) => `${f} → ${ch.join('+').toUpperCase()}`)
                .join(', ')}`}
              onClick={() => {
                setPalette(k)
                setFilter('all')
                setSelected(new Set(all.filter((r) => r.filter && p.map[r.filter]).map((r) => r.dataset_id)))
              }}
            >
              {p.label}
            </Chip>
          ))}
          {!palettes.length && (
            <Help topic="Palettes">HOO needs Hα and OIII datasets. SHO also needs SII.</Help>
          )}
          {palette && (
            <Button
              size="sm"
              onClick={() =>
                setLook({
                  target: { kind: 'palette', collection: id, project, name: palette as 'hoo' | 'sho' },
                  name: `${PALETTES[palette].label} from combined masters`,
                })
              }
            >
              {PALETTES[palette].label} at 100%
            </Button>
          )}
        </div>
        <div className={c.framing}>
          <div>
            <svg
              viewBox={`${x0} ${y0} ${x1 - x0} ${y1 - y0}`}
              className={c.framingSvg}
              role="img"
              aria-label="Fields on the sky"
            >
              {imaged.flatMap((r) => {
                const [tl, tr, , bl] = r.image_corners.map((p) => [-p[0], -p[1]])
                const m = `matrix(${tr[0] - tl[0]} ${tr[1] - tl[1]} ${bl[0] - tl[0]} ${bl[1] - tl[1]} ${tl[0]} ${tl[1]})`
                const img = (key: string) => (
                  <image
                    key={key}
                    href={r.image_url ?? `/api/v1/frames/${r.image}/preview`}
                    x={0}
                    y={0}
                    width={1}
                    height={1}
                    preserveAspectRatio="none"
                    opacity={pal ? 1 : imaged.length > 1 ? 0.8 : 0.95}
                    transform={m}
                  />
                )
                if (!pal || !r.filter) return [img(`i${r.dataset_id}`)]
                // palette: the grey sub multiplied by a pure channel colour, then the channels added (screen);
                // compositing keeps full resolution where an SVG filter would be drawn at the sky's tiny units
                return pal.map[r.filter].map((ch) => (
                  <g key={`i${r.dataset_id}${ch}`} style={{ mixBlendMode: 'screen' }}>
                    <g style={{ isolation: 'isolate' }}>
                      {img('img')}
                      <rect
                        x={0}
                        y={0}
                        width={1}
                        height={1}
                        transform={m}
                        style={{ fill: `var(--sst-ch-${ch})`, mixBlendMode: 'multiply' }}
                      />
                    </g>
                  </g>
                ))
              })}
              {outlines &&
                rows.map((r) => (
                  <polygon
                    key={r.dataset_id}
                    points={r.corners.map((p) => `${-p[0]},${-p[1]}`).join(' ')}
                    className={r.reference ? c.fieldRef : chosen.has(r.dataset_id) ? c.fieldShown : c.field}
                    vectorEffect="non-scaling-stroke"
                  />
                ))}
              {outlines &&
                rows.map((r, i) => {
                  const [ax, ay] = centre(r)
                  const near = (x: FramingRow) => {
                    const [bx, by] = centre(x)
                    return Math.hypot(ax - bx, ay - by) < r.fov_h / 6
                  }
                  if (rows.slice(0, i).some(near)) return null
                  const text = [...new Set(rows.filter(near).map((m) => short(m.label)))].join(' + ')
                  return (
                    <text
                      key={`t${r.dataset_id}`}
                      x={-ax}
                      y={-ay}
                      className={r.reference ? c.fieldLabelRef : c.fieldLabel}
                      fontSize={(x1 - x0) / 24}
                      textAnchor="middle"
                      dominantBaseline="middle"
                    >
                      {text}
                    </text>
                  )
                })}
            </svg>
            <div className={`${v.note} ${v.muted}`}>
              North up, east left · {shown.length} of {rows.length} shown
              {pal ? ` · ${pal.label} from single subs` : ''}
              {imaged.some((r) => !r.image_mirrored_known) ? ' · mirroring unknown for some' : ''}
            </div>
          </div>
          <div className={tb.pane}>
            <table className={`${v.table} ${tb.table} ${c.selectTable} cards`}>
              <thead>
                <tr>
                  {fth('name', 'Dataset')}
                  {fth('field', 'Field', tb.num)}
                  {fth('scale', 'Scale', tb.num)}
                  {fth('offset', 'Offset', tb.num)}
                  {fth('overlap', 'Overlap', tb.num)}
                  <th className={tb.act}>
                    <span className="visually-hidden">View</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {tableRows.map((r) => (
                  <tr
                    key={r.dataset_id}
                    className={chosen.has(r.dataset_id) ? c.rowShown : undefined}
                    aria-selected={chosen.has(r.dataset_id)}
                    onMouseDown={(e) => {
                      if (e.button !== 0) return
                      e.preventDefault()
                      pick(r, e)
                      setDragging(true)
                    }}
                    onMouseEnter={() => {
                      if (dragging) setSelected(new Set([...chosen, r.dataset_id]))
                    }}
                  >
                    <td>
                      <button
                        type="button"
                        className={c.rowButton}
                        onKeyDown={(e) =>
                          (e.key === ' ' || e.key === 'Enter') && (e.preventDefault(), pick(r, e))
                        }
                      >
                        <span className={r.reference ? c.refName : undefined}>{r.label}</span>
                      </button>
                      {r.reference && <span className={v.muted}> · reference</span>}
                      <div className={v.muted}>{r.solved} solved</div>
                    </td>
                    <td className={tb.num} data-label="Field">
                      {deg(r.fov_w)} × {deg(r.fov_h)}
                    </td>
                    <td className={tb.num} data-label="Scale">
                      {numText(r.scale, 2)}″/px
                    </td>
                    <td className={tb.num} data-label="Offset">
                      {r.reference ? '—' : `${numText(r.offset_arcmin)}′`}
                    </td>
                    <td className={tb.num} data-label="Overlap">
                      {pctText(r.overlap)}
                    </td>
                    <td className={tb.act}>
                      {(r.master_id || r.image) && (
                        <Button
                          size="sm"
                          variant="ghost"
                          onMouseDown={(e) => e.stopPropagation()}
                          onClick={() =>
                            setLook({
                              target: r.master_id
                                ? { kind: 'master', id: r.master_id }
                                : { kind: 'sub', sha: r.image! },
                              name: `${r.label} · ${r.master_id ? 'master' : 'best sub'}`,
                            })
                          }
                        >
                          100%
                        </Button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </Collapsible>
      {look && (
        <CloseLook
          target={look.target}
          name={look.name}
          mode={lookMode}
          onMode={setLookMode}
          onClose={() => setLook(null)}
        />
      )}
    </section>
  )
}

/** Capture software often names the same object differently between sessions (TestSoulNebula, IC 1848 - Soul
 * Nebula, Soul Nebula). Datasets only stack together under one name, so offer to merge the names. */
function MergeNames({
  id,
  datasets,
  onDone,
}: {
  id: number
  datasets: { target: string; sub_count: number }[]
  onDone: () => void
}) {
  const names = useMemo(() => {
    const n = new Map<string, number>()
    for (const ds of datasets) n.set(ds.target, (n.get(ds.target) ?? 0) + ds.sub_count)
    return [...n.entries()].sort((a, b) => b[1] - a[1])
  }, [datasets])
  const [into, setInto] = useState('')
  const qc = useQueryClient()
  const merge = useMutation({
    mutationFn: async (body: { names: string[]; into: string }) =>
      unwrap(await api.POST('/collections/{id}/merge-names', { params: { path: { id } }, body })),
    scope: { id: `collection-${id}` },
    meta: { failed: "Couldn't merge the names" },
    // every dataset takes the kept name at once (and this card goes); the files catch up in the background
    ...optimistic(qc, ({ names: from, into: to }: { names: string[]; into: string }) => [
      [
        ['collection', id],
        (o) => {
          const col = o as { datasets: { dataset: { target: string } }[] } | undefined
          if (!col) return o
          return {
            ...col,
            datasets: col.datasets.map((x) =>
              from.includes(x.dataset.target) ? { ...x, dataset: { ...x.dataset, target: to } } : x,
            ),
          }
        },
      ],
    ]),
    onSuccess: (_d, { into: to }) => {
      toast(`Merging names into “${to}”`)
      onDone()
    },
  })
  if (names.length < 2) return null
  const keep = into || names[0][0]
  const others = names.map(([n]) => n).filter((n) => n !== keep)

  return (
    <section className={`${v.card} ${v.cardPad}`}>
      <Collapsible id="collection-names" title="Names" meta={names.length}>
        <p className={`${v.muted} ${v.note}`}>
          {names.map(([n, subs]) => `${n} (${plural(subs, 'sub')})`).join(', ')}.{' '}
          <Help topic="Names">
            Only subs with the same name stack together. Merging names doesn't change files.
          </Help>
        </p>
        <div className={v.actions}>
          <Select
            value={keep}
            onChange={(e) => setInto(e.target.value)}
            aria-label="Name to keep"
            options={names.map(([n]) => ({ value: n, label: n }))}
          />
          <Button disabled={merge.isPending} onClick={() => merge.mutate({ names: others, into: keep })}>
            Merge {others.length} other name{others.length === 1 ? '' : 's'} into it
          </Button>
        </div>
      </Collapsible>
    </section>
  )
}

type Session = { night: string; rig: string; accepted_s: number; subs: number; filters: string[] }

const DAY = 86400000
const dayOf = (night: string) => new Date(`${night}T12:00:00Z`).getTime()

/** Date ticks for the axis (D05): the first of each month when the span is under ~14 months, else each year; one
 * kind of label, never a full date beside a month. */
function ticks(lo: number, hi: number): { at: number; label: string }[] {
  const out: { at: number; label: string }[] = []
  const a = new Date(lo)
  const months = (hi - lo) / (30 * DAY) < 14
  const d = months
    ? new Date(Date.UTC(a.getUTCFullYear(), a.getUTCMonth(), 1))
    : new Date(Date.UTC(a.getUTCFullYear(), 0, 1))
  const step = months ? Math.max(1, Math.ceil((hi - lo) / (30 * DAY) / 8)) : 1
  while (d.getTime() <= hi) {
    if (d.getTime() >= lo)
      out.push({
        at: d.getTime(),
        label: months ? monthText(d.toISOString().slice(0, 10)) : String(d.getUTCFullYear()),
      })
    if (months) d.setUTCMonth(d.getUTCMonth() + step)
    else d.setUTCFullYear(d.getUTCFullYear() + 1)
  }
  // the axis always says when it starts: the month (or year) at the left edge, unless a tick is already near it
  if (!out.length || out[0].at - lo > (hi - lo) * 0.12)
    out.unshift({
      at: lo,
      label: months ? monthText(a.toISOString().slice(0, 10)) : String(a.getUTCFullYear()),
    })
  return out
}

/** Every night on every rig (design v2 L2): a row per rig with its session count and integration, bars placed by
 * date on one shared axis, and a readout of the bar under the pointer. */
type Range = [string, string] | null

function Timeline({
  sessions,
  rigs,
  range,
  onRange,
}: {
  sessions: Session[]
  rigs: string[]
  range?: Range
  onRange?: (r: Range) => void
}) {
  const [hover, setHover] = useState<Session | null>(null)
  const inRange = (n: string) => !!range && n >= range[0] && n <= range[1]
  // click picks a night; shift-click stretches the range to it (006-DR-07)
  const pick = (n: string, extend: boolean) => {
    if (!onRange) return
    if (extend && range) onRange([n < range[0] ? n : range[0], n > range[1] ? n : range[1]])
    else onRange(range && range[0] === n && range[1] === n ? null : [n, n])
  }
  if (!sessions.length) return <p className={v.muted}>No sessions yet.</p>
  const t = sessions.map((x) => dayOf(x.night))
  const pad = 3 * DAY
  const lo = Math.min(...t) - pad
  const hi = Math.max(...t) + pad
  const max = Math.max(...sessions.map((x) => x.accepted_s), 1)
  const pct = (ms: number) => ((ms - lo) / (hi - lo)) * 100
  const first = sessions[0].night
  const last = sessions[sessions.length - 1].night
  return (
    <div className={c.tl}>
      {rigs.map((r) => {
        const mine = sessions.filter((x) => x.rig === r)
        const total = mine.reduce((n, x) => n + x.accepted_s, 0)
        return (
          <div key={r} className={c.tlRow}>
            <div>
              <div className={c.tlRig}>{r}</div>
              <div className={v.muted}>
                {plural(mine.length, 'session')} · {integrationText(total)}
              </div>
            </div>
            <div className={c.tlTrack}>
              {mine.map((x) => (
                <button
                  key={x.night}
                  type="button"
                  className={`${c.tlBar} ${hover === x || inRange(x.night) ? c.tlBarOn : ''}`}
                  aria-pressed={inRange(x.night)}
                  onClick={(e) => pick(x.night, e.shiftKey)}
                  style={{ left: `${pct(dayOf(x.night))}%`, height: `${12 + (x.accepted_s / max) * 88}%` }}
                  onMouseEnter={() => setHover(x)}
                  onFocus={() => setHover(x)}
                  onMouseLeave={() => setHover(null)}
                  onBlur={() => setHover(null)}
                  aria-label={`${nightText(x.night)}, ${r}: ${integrationText(x.accepted_s)}, ${x.subs} subs, ${x.filters.join(', ')}`}
                />
              ))}
            </div>
          </div>
        )
      })}
      <div className={c.tlRow}>
        <span />
        <div className={c.tlAxis}>
          {ticks(lo, hi).map((k) => (
            <span
              key={k.at}
              className={k.at === lo ? c.tlStart : undefined}
              style={{ left: `${pct(k.at)}%` }}
            >
              {k.label}
            </span>
          ))}
        </div>
      </div>
      <p className={c.tlReadout} aria-live="polite">
        {hover
          ? `${nightText(hover.night)} · ${hover.rig} · ${integrationText(hover.accepted_s)} · ${hover.subs} sub${hover.subs === 1 ? '' : 's'} · ${hover.filters.join(', ')}`
          : range
            ? `Sessions ${range[0] === range[1] ? `on ${nightText(range[0])}` : `from ${nightText(range[0])} to ${nightText(range[1])}`}`
            : `${plural(sessions.length, 'night')} from ${nightText(first)} to ${nightText(last)}`}
        {onRange && !hover && !range && (
          <>
            {' '}
            <Help topic="The sessions chart">
              Each bar is a night, as tall as its kept integration. Click one to show only that night below;
              shift-click another for a range.
            </Help>
          </>
        )}
        {range && onRange && (
          <>
            {' '}
            <Button size="sm" variant="ghost" onClick={() => onRange(null)}>
              Show all
            </Button>
          </>
        )}
      </p>
    </div>
  )
}
