// Projects on a collection's Overview (006-DR-20, spec 019 amendment 2026-10-15, amendment 2026-10-22): one card
// per season's project with its kind, rigs, months and goal bars; a ⋯ menu renames, changes the season or kind,
// merges, splits, marks done or deletes, each with Undo. Datasets not in a project sort into their seasons; the
// board moves datasets between projects by dragging.
import { useQuery } from '@tanstack/react-query'
import { useEffect, useRef, useState } from 'react'
import { api, unwrap } from '../../api/client'
import { useMenu } from '../../components/useMenu'
import { Collapsible } from '../../components/Collapsible'
import { Help } from '../../components/Help'
import { Modal } from '../../components/Modal'
import {
  Button,
  Chip,
  ConfirmButton,
  Field,
  FilterMeter,
  FilterMeterLegend,
  FilterTag,
  Input,
  SegmentedControl,
  Select,
} from '../../components/ui'
import { filterKey, filterName, sortFilters } from '../../components/filters'
import { integrationText, monthSpan, plural } from '../format'
import v from '../v2/v2.module.css'
import c from './collection.module.css'
import p from './projects.module.css'
import {
  type ProjectT,
  type ReviewT,
  useDeleteCombined,
  useImpact,
  useProjectActions,
  useProjects,
} from './Projects'
import { PutAwayConfirm, type Impact } from '../../components/PutAway'
import { toast } from '../../components/Toasts'
import { FILE_DELETED, VERBS } from '../changes/putAway'
import { useCanEdit } from '../settings/draft'

type FilterTime = { total_s: number; accepted_s: number; rejected_s: number }
type Ds = {
  dataset: { id: number; panel?: number | null; filter?: string | null; accepted_integration_s?: number }
  label: string
}
type Act = ReturnType<typeof useProjectActions>

/** Kept, waiting and goal for one filter, in seconds; pct when there's a goal. */
export function filterProgress(time: FilterTime | undefined, goalHours: number | undefined) {
  const kept = time?.accepted_s ?? 0
  const waiting = time ? Math.max(0, time.total_s - time.accepted_s - time.rejected_s) : 0
  const goal = (goalHours ?? 0) * 3600
  return { kept, waiting, goal, pct: goal ? Math.min(100, Math.round((kept / goal) * 100)) : null }
}

/** "Mosaic 2/4" or "Single field". */
export function kindText(x: Pick<ProjectT, 'kind' | 'panels' | 'planned_panels'>) {
  if (x.kind !== 'mosaic') return 'Single field'
  return `Mosaic ${x.panels.length}${x.planned_panels ? `/${x.planned_panels}` : ''}`
}

/** The filters a goal can be set for: the ones shot, then the rest of the canonical set (C06). */
const GOAL_FILTERS = ['L', 'R', 'G', 'B', 'Hα', 'OIII', 'SII', 'OSC']

/** Another filter a goal can be set for (018-DR-17): one the project's rigs shot through, or the canonical list
 * when no rig of the project is known; never one it already has. */
export function goalExtras(present: string[], rigFilters: string[]): string[] {
  const have = new Set(present.map(filterName))
  const known = rigFilters.filter(Boolean)
  const pool = known.length ? sortFilters([...new Set(known.map(filterName))]) : GOAL_FILTERS
  return pool.filter((f) => !have.has(f))
}

type SplitBy = 'rig' | 'panel' | 'datasets'
/** The ways a project can be split: only those that make two projects (two rigs, two panels, two datasets). */
export function splitOptions(x: Pick<ProjectT, 'rigs' | 'panels' | 'dataset_ids'>) {
  return [
    { value: 'rig' as SplitBy, label: `By rig (${x.rigs.length})`, disabled: x.rigs.length < 2 },
    { value: 'panel' as SplitBy, label: `By panel (${x.panels.length})`, disabled: x.panels.length < 2 },
    { value: 'datasets' as SplitBy, label: 'Chosen datasets', disabled: x.dataset_ids.length < 2 },
  ]
}

/** Planned panels only mean something for a mosaic: as set, or as worked out when the kind is Auto. */
export function panelsApply(kind: 'auto' | 'single' | 'mosaic', auto: string | null | undefined): boolean {
  return kind === 'mosaic' || (kind === 'auto' && auto === 'mosaic')
}

export function ProjectCards({
  collectionId,
  datasets,
  value,
  onChange,
  onArchive,
  onMasters,
}: {
  collectionId: number
  datasets: Ds[]
  value: number | null
  onChange: (id: number | null) => void
  /** Opens Archive files… for the collection: offered once its last open project is marked done. */
  onArchive?: () => void
  /** Opens the Masters tab, where the combined masters that block a delete are. */
  onMasters?: () => void
}) {
  const q = useProjects(collectionId)
  const act = useProjectActions(collectionId)
  const [arranging, setArranging] = useState(false)
  const [adding, setAdding] = useState(false)
  const [showDone, setShowDone] = useState(false)
  const [season, setSeason] = useState(() => String(new Date().getFullYear()))
  const [name, setName] = useState('')
  const projects = q.data?.projects ?? []
  const unassigned = q.data?.unassigned ?? []
  const review = q.data?.review ?? []
  const done = projects.filter((x) => x.done)
  const shown = projects.filter((x) => !x.done || showDone)
  const labels = new Map(datasets.map((d) => [d.dataset.id, d.label]))
  const byId = new Map(datasets.map((d) => [d.dataset.id, d.dataset]))
  return (
    <section className={`${v.card} ${v.cardPad}`}>
      <Collapsible
        id="collection-projects"
        title="Projects"
        meta={
          <span className={p.meta}>
            {plural(projects.length - done.length, 'project')}
            <Help topic="Projects">
              A project is one season of shooting this target: a season runs until a gap of more than 120
              days. Its kind is worked out from the panels unless you set it. Merge, split, delete and moves
              can be undone.
            </Help>
          </span>
        }
      >
        {review.map((g) => (
          <Held key={g.project_ids.join('-')} group={g} projects={projects} act={act} />
        ))}
        <div className={p.cards}>
          {shown.map((x) => (
            <ProjectCard
              key={x.id}
              project={x}
              others={projects.filter((o) => o.id !== x.id)}
              labels={labels}
              byId={byId}
              selected={value === x.id}
              onShow={() => onChange(value === x.id ? null : x.id)}
              act={act}
              collectionId={collectionId}
              onMasters={onMasters}
              onDone={() => {
                // the last open project done: the collection is finished, so its files are worth archiving
                if (onArchive && projects.filter((o) => !o.done && o.id !== x.id).length === 0)
                  toast('Every project here is done.', false, {
                    label: `${VERBS.archive.label}…`,
                    run: onArchive,
                  })
              }}
            />
          ))}
          {unassigned.length > 0 && (
            <article className={`${p.card} ${p.loose}`}>
              <header className={p.head}>
                <strong>Not in a project</strong>
                <span className={v.muted}>{plural(unassigned.length, 'dataset')}</span>
              </header>
              <div className={v.actions}>
                <Button size="sm" onClick={() => act.sort.mutate()} disabled={act.sort.isPending}>
                  Sort {unassigned.length} into seasons
                </Button>
              </div>
            </article>
          )}
        </div>
        {shown.some((x) => Object.keys(x.filter_time ?? {}).length) && (
          <FilterMeterLegend rejected={false} goal={shown.some((x) => Object.keys(x.goals ?? {}).length)} />
        )}
        {/* one way to add a project, one way to move datasets (C05) */}
        <div className={p.foot}>
          {adding ? (
            <form
              className={p.add}
              onSubmit={(e) => {
                e.preventDefault()
                if (!season.trim() && !name.trim()) return
                act.create.mutate({ season: season.trim(), name: name.trim() })
                setName('')
                setAdding(false)
              }}
            >
              <Input
                size_="sm"
                className={p.season}
                onKeyDown={(e) => e.key === 'Escape' && setAdding(false)}
                value={season}
                aria-label="Season"
                placeholder="Season"
                onChange={(e) => setSeason(e.target.value)}
              />
              <Input
                size_="sm"
                placeholder="Name (optional)"
                value={name}
                aria-label="New project name"
                onKeyDown={(e) => e.key === 'Escape' && setAdding(false)}
                onChange={(e) => setName(e.target.value)}
              />
              <Button
                size="sm"
                variant="primary"
                type="submit"
                disabled={(!season.trim() && !name.trim()) || act.create.isPending}
              >
                Add project
              </Button>
              <Button size="sm" onClick={() => setAdding(false)}>
                Cancel
              </Button>
            </form>
          ) : (
            <Button size="sm" onClick={() => setAdding(true)}>
              New project
            </Button>
          )}
          <span className={v.actions}>
            {done.length > 0 && (
              <Chip pressed={showDone} onClick={() => setShowDone(!showDone)} count={done.length}>
                Show done
              </Chip>
            )}
            {projects.length > 0 && (
              <Button size="sm" pressed={arranging} onClick={() => setArranging(!arranging)}>
                Arrange datasets…
              </Button>
            )}
          </span>
        </div>
        {arranging && <Board projects={projects} unassigned={unassigned} labels={labels} act={act} />}
      </Collapsible>
    </section>
  )
}

/** Projects of one season held apart when seasons were joined: merge them, or keep them apart. */
function Held({ group, projects, act }: { group: ReviewT; projects: ProjectT[]; act: Act }) {
  const named = group.project_ids.map((id) => projects.find((x) => x.id === id)?.label ?? `Project ${id}`)
  return (
    <div className={p.held} role="status">
      <span>
        <strong>Kept apart</strong> {named.join(' and ')} · {group.reasons.join('; ')}
      </span>
      <span className={v.actions}>
        <Button
          size="sm"
          disabled={!group.mergeable || act.merge.isPending}
          title={group.mergeable ? undefined : 'One of them is linked to a finished image'}
          onClick={() =>
            act.merge.mutate({ into: group.into, from: group.project_ids.filter((id) => id !== group.into) })
          }
        >
          Merge
        </Button>
        <Button
          size="sm"
          onClick={() => group.project_ids.forEach((id) => act.patch.mutate({ id, needs_review: false }))}
        >
          Keep apart
        </Button>
      </span>
    </div>
  )
}

type Mode = 'rename' | 'season' | 'kind' | 'goals' | 'delete' | 'merge' | 'split' | null

function ProjectCard({
  project: x,
  others,
  labels,
  byId,
  selected,
  onShow,
  act,
  collectionId,
  onMasters,
  onDone,
}: {
  project: ProjectT
  others: ProjectT[]
  labels: Map<number, string>
  byId: Map<number, Ds['dataset']>
  selected: boolean
  onShow: () => void
  act: Act
  collectionId: number
  onMasters?: () => void
  onDone: () => void
}) {
  const [mode, setMode] = useState<Mode>(null)
  // every item in the menu changes the project: a read-only user gets none of them
  const canEdit = useCanEdit()
  const filters = sortFilters([
    ...new Set([...Object.keys(x.filter_time ?? {}), ...Object.keys(x.goals ?? {})]),
  ])
  const most = Math.max(1, ...filters.map((f) => x.filter_time?.[f]?.total_s ?? 0))
  const close = () => setMode(null)
  return (
    <article className={`${p.card} ${selected ? p.selected : ''} ${x.done ? p.done : ''}`}>
      <header className={p.head}>
        <div className={p.title}>
          <strong>{x.label || x.name}</strong>
          <Chip title={x.kind_override ? 'Set by you' : 'Worked out from the panels'}>
            {kindText(x)}
            {!x.kind_override && <span className={p.auto}>auto</span>}
          </Chip>
          {x.done && <Chip tone="ok">Done</Chip>}
        </div>
        <span className={p.right}>
          <span className={p.figure}>{integrationText(x.accepted_integration_s)}</span>
          {canEdit && (
            <Menu
              label={x.label || x.name}
              items={[
                ['Rename', () => setMode('rename')],
                ['Season', () => setMode('season')],
                ['Kind', () => setMode('kind')],
                ['Goals', () => setMode('goals')],
                ...(others.length ? ([['Merge into…', () => setMode('merge')]] as const) : []),
                ...(splitOptions(x).some((o) => !o.disabled)
                  ? ([['Split…', () => setMode('split')]] as const)
                  : []),
                [
                  x.done ? VERBS.done.restore : VERBS.done.label,
                  () =>
                    act.patch.mutate({ id: x.id, done: !x.done }, { onSuccess: () => !x.done && onDone() }),
                ],
                [`${VERBS.delete.label}…`, () => setMode('delete')],
              ]}
            />
          )}
        </span>
      </header>
      <div className={`muted ${p.facts}`}>
        {[
          x.missing_panels.length ? `missing ${x.missing_panels.join(', ')}` : '',
          x.rigs.join(', '),
          monthSpan(x.first_night, x.last_night),
        ]
          .filter(Boolean)
          .join(' · ') || 'No datasets yet'}
      </div>

      {mode === null && filters.length > 0 && (
        <div className={p.bars}>
          {filters.map((f) => {
            const g = filterProgress(x.filter_time?.[f], x.goals?.[f])
            return (
              <FilterMeter
                key={f}
                filter={f}
                kept={g.kept}
                waiting={g.waiting}
                goal={g.goal || null}
                max={most}
                value={
                  g.goal ? `${integrationText(g.kept)} / ${integrationText(g.goal)}` : integrationText(g.kept)
                }
                detail={
                  g.goal
                    ? `${integrationText(g.kept)} kept of a ${integrationText(g.goal)} goal, ${g.pct}%`
                    : `${integrationText(g.kept)} kept`
                }
              />
            )
          })}
        </div>
      )}
      {/* a mosaic shows each panel's filters, not one bar summed across panels (C07) */}
      {mode === null && x.kind === 'mosaic' && <PanelMatrix project={x} byId={byId} />}

      {mode === 'rename' && (
        <OneField
          label="Name"
          initial={x.own_name}
          placeholder="Optional, after the season"
          onSave={(name) => (act.patch.mutate({ id: x.id, name }), close())}
          onCancel={close}
        />
      )}
      {mode === 'season' && (
        <OneField
          label="Season"
          initial={x.season}
          placeholder="2026 or 2025–26"
          onSave={(season) => (act.patch.mutate({ id: x.id, season }), close())}
          onCancel={close}
        />
      )}
      {mode === 'kind' && <KindForm project={x} act={act} onDone={close} />}
      {mode === 'goals' && <GoalsForm project={x} filters={filters} act={act} onDone={close} />}
      {mode === 'delete' && (
        <DeleteProject
          project={x}
          act={act}
          collectionId={collectionId}
          onMasters={onMasters}
          onDone={close}
        />
      )}
      {mode === 'merge' && <MergeDialog project={x} others={others} act={act} onClose={close} />}
      {mode === 'split' && <SplitDialog project={x} labels={labels} act={act} onClose={close} />}

      {mode === null && (
        <div className={v.actions}>
          <Button size="sm" variant="ghost" pressed={selected} onClick={onShow}>
            {selected ? 'Showing only this' : 'Show only this'}
          </Button>
        </div>
      )}
    </article>
  )
}

/** A mosaic's panels against its filters: kept integration in each, "—" where a panel has none, and the planned
 * panels not shot yet as empty rows. */
function PanelMatrix({ project: x, byId }: { project: ProjectT; byId: Map<number, Ds['dataset']> }) {
  const cell = new Map<string, number>()
  const filters = new Set<string>()
  const panels = new Set<number>([...x.panels, ...x.missing_panels])
  for (const id of x.dataset_ids) {
    const d = byId.get(id)
    if (!d || d.panel == null) continue
    const f = filterName(d.filter) || '—'
    filters.add(f)
    panels.add(d.panel)
    const k = `${d.panel}|${f}`
    cell.set(k, (cell.get(k) ?? 0) + (d.accepted_integration_s ?? 0))
  }
  const cols = sortFilters([...filters])
  const rows = [...panels].sort((a, b) => a - b)
  if (!rows.length || !cols.length) return null
  return (
    <div className={p.matrixWrap}>
      <table className={p.matrix} aria-label={`${x.label}: kept integration per panel and filter`}>
        <thead>
          <tr>
            <th scope="col">Panel</th>
            {cols.map((f) => (
              <th key={f} scope="col">
                {filterKey(f) ? <FilterTag filter={f} plain /> : f}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((n) => (
            <tr key={n}>
              <th scope="row">{n}</th>
              {cols.map((f) => {
                const s = cell.get(`${n}|${f}`)
                return <td key={f}>{s ? integrationText(s) : '—'}</td>
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

/** The ⋯ menu: closes on a choice, Escape or a click elsewhere. Also the collection page's header menu. */
export function Menu({ label, items }: { label: string; items: (readonly [string, () => void])[] }) {
  const [open, setOpen] = useState(false)
  const box = useRef<HTMLSpanElement>(null)
  const { button: menuButton, menu: menuBox, onKeyDown: menuKeys } = useMenu(open, setOpen)
  useEffect(() => {
    if (!open) return
    const away = (e: PointerEvent) => !box.current?.contains(e.target as Node) && setOpen(false)
    document.addEventListener('pointerdown', away)
    return () => document.removeEventListener('pointerdown', away)
  }, [open])
  return (
    <span ref={box} className={p.menuBox}>
      <button
        type="button"
        ref={menuButton}
        className={p.dots}
        aria-label={`More for ${label}`}
        aria-haspopup="menu"
        aria-expanded={open}
        onClick={() => setOpen(!open)}
      >
        ⋯
      </button>
      {open && (
        <span
          className={p.menu}
          role="menu"
          aria-label={label}
          ref={menuBox}
          tabIndex={-1}
          onKeyDown={menuKeys}
        >
          {items.map(([text, run]) => (
            <button
              key={text}
              type="button"
              role="menuitem"
              tabIndex={-1}
              onClick={() => {
                setOpen(false)
                // a dialog the item opens gives focus back to the ⋯ button, not to an item that's gone
                menuButton.current?.focus()
                run()
              }}
            >
              {text}
            </button>
          ))}
        </span>
      )}
    </span>
  )
}

function OneField({
  label,
  initial,
  placeholder,
  onSave,
  onCancel,
}: {
  label: string
  initial: string
  placeholder: string
  onSave: (value: string) => void
  onCancel: () => void
}) {
  const [value, setValue] = useState(initial)
  return (
    <form
      className={p.form}
      onSubmit={(e) => {
        e.preventDefault()
        onSave(value.trim())
      }}
    >
      <label>
        {label}{' '}
        <Input
          size_="sm"
          value={value}
          placeholder={placeholder}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={(e) => e.key === 'Escape' && onCancel()}
        />
      </label>
      <span className={v.actions}>
        <Button size="sm" variant="primary" type="submit">
          Save
        </Button>
        <Button size="sm" type="button" onClick={onCancel}>
          Cancel
        </Button>
      </span>
    </form>
  )
}

function KindForm({ project: x, act, onDone }: { project: ProjectT; act: Act; onDone: () => void }) {
  const [kind, setKind] = useState<'auto' | 'single' | 'mosaic'>(
    (x.kind_override as 'single' | 'mosaic' | null) ?? 'auto',
  )
  const [panels, setPanels] = useState(x.planned_panels ? String(x.planned_panels) : '')
  return (
    <form
      className={p.form}
      onSubmit={(e) => {
        e.preventDefault()
        const mosaic = panelsApply(kind, x.kind_auto)
        act.patch.mutate({ id: x.id, kind, planned_panels: mosaic ? Number(panels) || null : null })
        onDone()
      }}
    >
      <SegmentedControl
        size="sm"
        label="Kind"
        value={kind}
        onChange={setKind}
        options={[
          { value: 'auto', label: `Auto (${x.kind_auto === 'mosaic' ? 'mosaic' : 'single'})` },
          { value: 'single', label: 'Single field' },
          { value: 'mosaic', label: 'Mosaic' },
        ]}
      />
      <label>
        Panels{' '}
        <Input
          size_="sm"
          className={p.num}
          type="number"
          min={1}
          max={100}
          placeholder={panelsApply(kind, x.kind_auto) ? 'planned' : 'mosaic only'}
          disabled={!panelsApply(kind, x.kind_auto)}
          value={panelsApply(kind, x.kind_auto) ? panels : ''}
          onChange={(e) => setPanels(e.target.value)}
        />
      </label>
      <span className={v.actions}>
        <Button size="sm" variant="primary" type="submit">
          Save
        </Button>
        <Button size="sm" type="button" onClick={onDone}>
          Cancel
        </Button>
      </span>
    </form>
  )
}

/** A goal per filter the project has, in hours (C06): the filters come from its datasets; another one is
 * chosen from the known filters, never typed. */
function GoalsForm({
  project: x,
  filters,
  act,
  onDone,
}: {
  project: ProjectT
  filters: string[]
  act: Act
  onDone: () => void
}) {
  const [goals, setGoals] = useState<Record<string, string>>(() =>
    Object.fromEntries(filters.map((f) => [f, x.goals?.[f] ? String(x.goals[f]) : ''])),
  )
  const rigs = useQuery({ queryKey: ['rigs'], queryFn: async () => unwrap(await api.GET('/rigs')) })
  const rigFilters = (rigs.data ?? []).filter((r) => x.rigs.includes(r.name)).flatMap((r) => r.filters ?? [])
  const extras = goalExtras(Object.keys(goals), rigFilters)
  return (
    <form
      className={p.form}
      onSubmit={(e) => {
        e.preventDefault()
        act.patch.mutate({
          id: x.id,
          goals: Object.fromEntries(Object.entries(goals).map(([f, h]) => [f, h.trim() ? Number(h) : null])),
        })
        onDone()
      }}
    >
      <fieldset className={p.goals}>
        <legend>Goals, hours kept</legend>
        {sortFilters(Object.keys(goals)).map((f) => (
          <Field key={f} inline label={<FilterTag filter={f} plain />}>
            <span className={p.hours}>
              <Input
                size_="sm"
                className={p.num}
                type="number"
                min={0}
                max={1000}
                step={0.5}
                inputMode="decimal"
                aria-label={`Goal for ${filterName(f)}, hours`}
                value={goals[f]}
                onChange={(e) => setGoals({ ...goals, [f]: e.target.value })}
              />
              <span aria-hidden="true">h</span>
            </span>
          </Field>
        ))}
        {extras.length > 0 && (
          <Select
            size_="sm"
            aria-label="Add a goal for another filter"
            value=""
            onChange={(e) => e.target.value && setGoals({ ...goals, [e.target.value]: '' })}
            options={[
              { value: '', label: 'Another filter…' },
              ...extras.map((f) => ({ value: f, label: f })),
            ]}
          />
        )}
      </fieldset>
      <span className={v.actions}>
        <Button size="sm" variant="primary" type="submit">
          Save
        </Button>
        <Button size="sm" type="button" onClick={onDone}>
          Cancel
        </Button>
      </span>
    </form>
  )
}

/** The three lines for deleting a project, from its impact. */
export function projectImpactLines(
  x: Pick<ProjectT, 'goals'>,
  i: { datasets: number; finished: string[] },
): Impact {
  const goals = Object.keys(x.goals ?? {}).length > 0
  const links = [
    goals ? 'Its goals go with it.' : '',
    i.finished.length ? `No longer linked to ${i.finished.join(', ')}.` : '',
  ].filter(Boolean)
  return {
    records: `${plural(i.datasets, 'dataset')} ${i.datasets === 1 ? 'stays' : 'stay'} in the collection, as “Not in a project”.`,
    links: links.join(' ') || 'No links or goals.',
  }
}

/** Delete, asking first (006-DR-40): what it touches, or why it can't go — with its combined masters to delete. */
function DeleteProject({
  project: x,
  act,
  collectionId,
  onMasters,
  onDone,
}: {
  project: ProjectT
  act: Act
  collectionId: number
  onMasters?: () => void
  onDone: () => void
}) {
  const impact = useImpact(x.id)
  const i = impact.data
  const blocked = !!i && i.combined.length > 0
  return (
    <PutAwayConfirm
      verb="delete"
      name={x.label || x.name}
      impact={i ? projectImpactLines(x, i) : null}
      refused={
        blocked
          ? `It has combined masters (${i.combined.join(', ')}). Delete them first, or merge it.`
          : undefined
      }
      onConfirm={() => {
        act.remove.mutate({ id: x.id, label: x.label || x.name })
        onDone()
      }}
      onClose={onDone}
    >
      {blocked && <CombinedToDelete collectionId={collectionId} project={x.id} onMasters={onMasters} />}
    </PutAwayConfirm>
  )
}

/** A project's combined masters, each with Delete: the file goes for good. */
function CombinedToDelete({
  collectionId,
  project,
  onMasters,
}: {
  collectionId: number
  project: number
  onMasters?: () => void
}) {
  const q = useQuery({
    queryKey: ['combined', collectionId, project],
    queryFn: async () =>
      unwrap(
        await api.GET('/collections/{id}/combined', {
          params: { path: { id: collectionId }, query: { project } },
        }),
      ),
  })
  const remove = useDeleteCombined()
  const canEdit = useCanEdit()
  return (
    <>
      <ul className={p.combinedList}>
        {(q.data?.combined ?? []).map((m) => {
          const name = `${filterName(m.filter)} combined v${m.version}`
          return (
            <li key={m.id}>
              <span>{name}</span>
              {canEdit && (
                <ConfirmButton
                  size="sm"
                  variant="danger"
                  question={<>{FILE_DELETED}</>}
                  confirm={`Delete ${name}`}
                  onConfirm={() => remove.mutate({ id: m.id, name })}
                >
                  Delete…
                </ConfirmButton>
              )}
            </li>
          )
        })}
      </ul>
      {onMasters && (
        <span>
          <Button size="sm" variant="link" onClick={onMasters}>
            Open the collection's masters
          </Button>
        </span>
      )}
    </>
  )
}

function MergeDialog({
  project: x,
  others,
  act,
  onClose,
}: {
  project: ProjectT
  others: ProjectT[]
  act: Act
  onClose: () => void
}) {
  const [into, setInto] = useState(others[0]?.id ?? 0)
  const impact = useImpact(x.id, into || null, !!into)
  const i = impact.data
  const target = others.find((o) => o.id === into)
  const blocked = !!i?.finished.length
  return (
    <Modal label={`Merge ${x.label}`} onClose={onClose} size="sm">
      <div className={p.dialog}>
        <h2 className={p.dialogTitle}>Merge {x.label} into…</h2>
        <Field inline label="Project">
          <Select
            value={into}
            onChange={(e) => setInto(Number(e.target.value))}
            options={others.map((o) => ({ value: o.id, label: o.label }))}
          />
        </Field>
        <ul className={p.impact} aria-label="What merging changes">
          <li>
            {plural(x.dataset_ids.length, 'dataset')} move into {target?.label}; {target?.label} keeps its
            name.
          </li>
          {i?.combined.length ? <li>Combined masters move with them: {i.combined.join(', ')}.</li> : null}
          {i?.goal_conflicts.map((g) => (
            <li key={g} className={p.warn}>
              Goals differ, the larger is kept: {g}.
            </li>
          ))}
          {blocked && (
            <li className={p.warn}>
              Linked to {i.finished.join(', ')}: a merge would change what that image was made from, so it
              can't be merged.
            </li>
          )}
        </ul>
        <span className={v.actions}>
          <Button
            variant="primary"
            disabled={!into || blocked || !i || act.merge.isPending}
            onClick={() => {
              act.merge.mutate({ into, from: [x.id] })
              onClose()
            }}
          >
            Merge
          </Button>
          <Button onClick={onClose}>Cancel</Button>
        </span>
      </div>
    </Modal>
  )
}

function SplitDialog({
  project: x,
  labels,
  act,
  onClose,
}: {
  project: ProjectT
  labels: Map<number, string>
  act: Act
  onClose: () => void
}) {
  const ways = splitOptions(x)
  const [by, setBy] = useState<SplitBy>(ways.find((o) => !o.disabled)?.value ?? 'datasets')
  const [chosen, setChosen] = useState<number[]>([])
  const [name, setName] = useState('')
  const impact = useImpact(x.id)
  const i = impact.data
  const ok =
    by === 'rig'
      ? x.rigs.length > 1
      : by === 'panel'
        ? x.panels.length > 1
        : chosen.length > 0 && chosen.length < x.dataset_ids.length
  return (
    <Modal label={`Split ${x.label}`} onClose={onClose} size="sm">
      <div className={p.dialog}>
        <h2 className={p.dialogTitle}>Split {x.label}</h2>
        <SegmentedControl label="Split by" value={by} onChange={setBy} options={ways} />
        {by === 'datasets' && (
          <>
            <ul className={p.choose}>
              {x.dataset_ids.map((id) => (
                <li key={id}>
                  <label>
                    <input
                      type="checkbox"
                      checked={chosen.includes(id)}
                      onChange={(e) =>
                        setChosen(e.target.checked ? [...chosen, id] : chosen.filter((y) => y !== id))
                      }
                    />{' '}
                    {labels.get(id) ?? `Dataset ${id}`}
                  </label>
                </li>
              ))}
            </ul>
            <Field inline label="Name">
              <Input placeholder="Optional" value={name} onChange={(e) => setName(e.target.value)} />
            </Field>
          </>
        )}
        <ul className={p.impact} aria-label="What splitting changes">
          <li>
            {by === 'datasets'
              ? 'The chosen datasets go to a new project'
              : `Each other ${by} goes to a new project; the one with the most integration stays`}{' '}
            in {x.season || 'the same season'}.
          </li>
          {Object.keys(x.goals ?? {}).length > 0 && <li className={p.warn}>Goals stay on {x.label}.</li>}
          {i?.finished.length ? (
            <li className={p.warn}>
              {i.finished.join(', ')} stays linked to {x.label}.
            </li>
          ) : null}
        </ul>
        <span className={v.actions}>
          <Button
            variant="primary"
            disabled={!ok || act.split.isPending}
            onClick={() => {
              act.split.mutate({ id: x.id, by, dataset_ids: by === 'datasets' ? chosen : [], name })
              onClose()
            }}
          >
            Split
          </Button>
          <Button onClick={onClose}>Cancel</Button>
        </span>
      </div>
    </Modal>
  )
}

/** Move datasets between projects by dragging (or Alt+↑/↓ within one). */
function Board({
  projects,
  unassigned,
  labels,
  act,
}: {
  projects: ProjectT[]
  unassigned: number[]
  labels: Map<number, string>
  act: Act
}) {
  const [dragged, setDragged] = useState<number | null>(null)

  /** Put dataset `ds` into project `to` before dataset `before` (or at the end); null takes it out. */
  const place = (ds: number, to: number | null, before: number | null) => {
    const from = projects.find((x) => x.dataset_ids.includes(ds))
    if (to == null) {
      if (from) act.setDatasets.mutate({ id: from.id, ids: from.dataset_ids.filter((x) => x !== ds) })
      return
    }
    const target = projects.find((x) => x.id === to)
    if (!target) return
    const ids = target.dataset_ids.filter((x) => x !== ds)
    const at = before == null ? ids.length : Math.max(0, ids.indexOf(before))
    ids.splice(at, 0, ds)
    act.setDatasets.mutate({ id: to, ids })
  }

  const column = (x: ProjectT | null) => {
    const ids = x ? x.dataset_ids : unassigned
    return (
      <div
        key={x?.id ?? 'none'}
        className={`${p.card} ${c.projectCol}`}
        onDragOver={(e) => e.preventDefault()}
        onDrop={(e) => {
          e.preventDefault()
          if (dragged != null && (e.target as HTMLElement).closest('li') == null)
            place(dragged, x?.id ?? null, null)
          setDragged(null)
        }}
      >
        <strong>{x ? x.label : 'Not in a project'}</strong>
        <ul className={c.projectList}>
          {ids.map((ds, i) => (
            <li key={ds} className={dragged === ds ? c.dragging : undefined}>
              <button
                type="button"
                className={c.projectItem}
                onDragOver={(e) => e.preventDefault()}
                onDrop={(e) => {
                  e.preventDefault()
                  e.stopPropagation()
                  if (dragged != null && dragged !== ds) place(dragged, x?.id ?? null, ds)
                  setDragged(null)
                }}
                draggable
                title="Drag to another project, or Alt+↑/↓ to reorder"
                onDragStart={() => setDragged(ds)}
                onDragEnd={() => setDragged(null)}
                onKeyDown={(e) => {
                  if (!e.altKey || !x) return
                  const order = [...x.dataset_ids]
                  if (e.key === 'ArrowUp' && i > 0) [order[i - 1], order[i]] = [order[i], order[i - 1]]
                  else if (e.key === 'ArrowDown' && i < order.length - 1)
                    [order[i + 1], order[i]] = [order[i], order[i + 1]]
                  else return
                  e.preventDefault()
                  act.setDatasets.mutate({ id: x.id, ids: order })
                }}
              >
                {labels.get(ds) ?? `Dataset ${ds}`}
              </button>
            </li>
          ))}
          {!ids.length && <li className={v.muted}>Drop datasets here</li>}
        </ul>
      </div>
    )
  }

  return (
    <div className={c.projectCols}>
      {projects.map((x) => column(x))}
      {column(null)}
    </div>
  )
}
