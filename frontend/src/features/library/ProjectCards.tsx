// Projects on a collection's Overview (006-DR-20, spec 019 amendment 2026-10-15, amendment 2026-10-22): one card
// per season's project with its kind, rigs, months and goal bars; a ⋯ menu renames, changes the season or kind,
// merges, splits, marks done or deletes, each with Undo. Datasets not in a project sort into their seasons; the
// board moves datasets between projects by dragging.
import { useEffect, useRef, useState } from 'react'
import { Collapsible } from '../../components/Collapsible'
import { Help } from '../../components/Help'
import { Modal } from '../../components/Modal'
import { Button, ConfirmButton } from '../../components/ui'
import { integrationText, monthSpan } from '../format'
import v from '../v2/v2.module.css'
import c from './collection.module.css'
import s from './library.module.css'
import p from './projects.module.css'
import { type ProjectT, type ReviewT, useImpact, useProjectActions, useProjects } from './Projects'

type FilterTime = { total_s: number; accepted_s: number; rejected_s: number }
type Ds = { dataset: { id: number }; label: string }
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

const plural = (n: number, w: string) => `${n} ${w}${n === 1 ? '' : 's'}`

export function ProjectCards({
  collectionId,
  datasets,
  value,
  onChange,
}: {
  collectionId: number
  datasets: Ds[]
  value: number | null
  onChange: (id: number | null) => void
}) {
  const q = useProjects(collectionId)
  const act = useProjectActions(collectionId)
  const [arranging, setArranging] = useState(false)
  const [showDone, setShowDone] = useState(false)
  const [season, setSeason] = useState(() => String(new Date().getFullYear()))
  const [name, setName] = useState('')
  const projects = q.data?.projects ?? []
  const unassigned = q.data?.unassigned ?? []
  const review = q.data?.review ?? []
  const done = projects.filter((x) => x.done)
  const shown = projects.filter((x) => !x.done || showDone)
  const labels = new Map(datasets.map((d) => [d.dataset.id, d.label]))
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
              selected={value === x.id}
              onShow={() => onChange(value === x.id ? null : x.id)}
              act={act}
            />
          ))}
          {unassigned.length > 0 && (
            <article className={`${p.card} ${p.loose}`}>
              <header className={p.head}>
                <strong>Not in a project</strong>
                <span className={v.mono}>{plural(unassigned.length, 'dataset')}</span>
              </header>
              <div className={v.actions}>
                <Button variant="primary" onClick={() => act.sort.mutate()} disabled={act.sort.isPending}>
                  Sort {unassigned.length} into seasons
                </Button>
                <Button onClick={() => setArranging(true)}>Arrange…</Button>
              </div>
            </article>
          )}
        </div>
        <div className={p.foot}>
          <form
            className={p.add}
            onSubmit={(e) => {
              e.preventDefault()
              if (!season.trim() && !name.trim()) return
              act.create.mutate({ season: season.trim(), name: name.trim() })
              setName('')
            }}
          >
            <input
              className={`${v.input} ${p.season}`}
              value={season}
              aria-label="Season"
              placeholder="Season"
              onChange={(e) => setSeason(e.target.value)}
            />
            <input
              className={v.input}
              placeholder="Name (optional)"
              value={name}
              aria-label="New project name"
              onChange={(e) => setName(e.target.value)}
            />
            <Button type="submit" disabled={(!season.trim() && !name.trim()) || act.create.isPending}>
              Add project
            </Button>
          </form>
          <span className={v.actions}>
            {done.length > 0 && (
              <button
                type="button"
                className={v.pill}
                aria-pressed={showDone}
                onClick={() => setShowDone(!showDone)}
              >
                Done ({done.length})
              </button>
            )}
            {projects.length > 0 && (
              <button
                type="button"
                className={v.pill}
                aria-pressed={arranging}
                onClick={() => setArranging(!arranging)}
              >
                Arrange datasets…
              </button>
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
          disabled={!group.mergeable || act.merge.isPending}
          title={group.mergeable ? undefined : 'One of them is linked to a finished image'}
          onClick={() =>
            act.merge.mutate({ into: group.into, from: group.project_ids.filter((id) => id !== group.into) })
          }
        >
          Merge
        </Button>
        <Button
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
  selected,
  onShow,
  act,
}: {
  project: ProjectT
  others: ProjectT[]
  labels: Map<number, string>
  selected: boolean
  onShow: () => void
  act: Act
}) {
  const [mode, setMode] = useState<Mode>(null)
  const filters = [...new Set([...Object.keys(x.filter_time ?? {}), ...Object.keys(x.goals ?? {})])].sort()
  const most = Math.max(1, ...filters.map((f) => x.filter_time?.[f]?.total_s ?? 0))
  const close = () => setMode(null)
  return (
    <article className={`${p.card} ${selected ? p.selected : ''} ${x.done ? p.done : ''}`}>
      <header className={p.head}>
        <div className={p.title}>
          <strong>{x.label}</strong>
          <span className={p.badge} title={x.kind_override ? 'Set by you' : 'Worked out from the panels'}>
            {kindText(x)}
            {!x.kind_override && <span className={p.auto}>auto</span>}
          </span>
          {x.done && <span className={p.badge}>Done</span>}
        </div>
        <span className={p.right}>
          <span className={v.mono}>{integrationText(x.accepted_integration_s)}</span>
          <Menu
            label={x.label}
            items={[
              ['Rename', () => setMode('rename')],
              ['Season', () => setMode('season')],
              ['Kind', () => setMode('kind')],
              ['Goals', () => setMode('goals')],
              ...(others.length ? ([['Merge into…', () => setMode('merge')]] as const) : []),
              ['Split…', () => setMode('split')],
              [x.done ? 'Not done' : 'Done', () => act.patch.mutate({ id: x.id, done: !x.done })],
              ['Delete', () => setMode('delete')],
            ]}
          />
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
        <ul className={p.bars}>
          {filters.map((f) => {
            const g = filterProgress(x.filter_time?.[f], x.goals?.[f])
            const scale = g.goal || most
            const pct = (n: number) => `${Math.min(100, (n / scale) * 100)}%`
            return (
              <li key={f} className={p.row}>
                <strong>{f}</strong>
                <span
                  className={`${s.bar} ${p.bar}`}
                  role={g.goal ? 'progressbar' : undefined}
                  aria-label={g.goal ? `${f} goal` : undefined}
                  aria-valuemin={g.goal ? 0 : undefined}
                  aria-valuemax={g.goal ? 100 : undefined}
                  aria-valuenow={g.goal ? (g.pct ?? 0) : undefined}
                >
                  <span className={s.barOk} style={{ width: pct(g.kept) }} />
                  <span className={s.barWait} style={{ width: pct(g.waiting) }} />
                </span>
                <span className={v.mono}>
                  {g.goal ? (
                    <>
                      <span className={g.kept >= g.goal ? v.ok : v.accent}>{integrationText(g.kept)}</span> of{' '}
                      {integrationText(g.goal)}
                    </>
                  ) : (
                    integrationText(g.kept)
                  )}
                </span>
              </li>
            )
          })}
        </ul>
      )}

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
      {mode === 'delete' && <DeleteRow project={x} act={act} onDone={close} />}
      {mode === 'merge' && <MergeDialog project={x} others={others} act={act} onClose={close} />}
      {mode === 'split' && <SplitDialog project={x} labels={labels} act={act} onClose={close} />}

      {mode === null && (
        <div className={v.actions}>
          <button type="button" className={v.pill} aria-pressed={selected} onClick={onShow}>
            {selected ? 'Showing only this' : 'Show only this'}
          </button>
        </div>
      )}
    </article>
  )
}

/** The ⋯ menu: closes on a choice, Escape or a click elsewhere. */
function Menu({ label, items }: { label: string; items: (readonly [string, () => void])[] }) {
  const [open, setOpen] = useState(false)
  const box = useRef<HTMLSpanElement>(null)
  useEffect(() => {
    if (!open) return
    const away = (e: PointerEvent) => !box.current?.contains(e.target as Node) && setOpen(false)
    const key = (e: KeyboardEvent) => e.key === 'Escape' && setOpen(false)
    document.addEventListener('pointerdown', away)
    document.addEventListener('keydown', key)
    return () => {
      document.removeEventListener('pointerdown', away)
      document.removeEventListener('keydown', key)
    }
  }, [open])
  return (
    <span ref={box} className={p.menuBox}>
      <button
        type="button"
        className={p.dots}
        aria-label={`More for ${label}`}
        aria-haspopup="menu"
        aria-expanded={open}
        onClick={() => setOpen(!open)}
      >
        ⋯
      </button>
      {open && (
        <span className={p.menu} role="menu" aria-label={label}>
          {items.map(([text, run]) => (
            <button
              key={text}
              type="button"
              role="menuitem"
              onClick={() => {
                setOpen(false)
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
        <input
          className={v.input}
          value={value}
          placeholder={placeholder}
          onChange={(e) => setValue(e.target.value)}
        />
      </label>
      <span className={v.actions}>
        <Button variant="primary" type="submit">
          Save
        </Button>
        <Button type="button" onClick={onCancel}>
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
        act.patch.mutate({ id: x.id, kind, planned_panels: Number(panels) || null })
        onDone()
      }}
    >
      <span className={v.pills} role="group" aria-label="Kind">
        {(
          [
            ['auto', `Auto (${x.kind_auto === 'mosaic' ? 'mosaic' : 'single'})`],
            ['single', 'Single field'],
            ['mosaic', 'Mosaic'],
          ] as const
        ).map(([k, text]) => (
          <button
            key={k}
            type="button"
            className={v.pill}
            aria-pressed={kind === k}
            onClick={() => setKind(k)}
          >
            {text}
          </button>
        ))}
      </span>
      <label>
        Panels{' '}
        <input
          className={`${v.input} ${p.num}`}
          type="number"
          min={1}
          max={100}
          placeholder="planned"
          value={panels}
          onChange={(e) => setPanels(e.target.value)}
        />
      </label>
      <span className={v.actions}>
        <Button variant="primary" type="submit">
          Save
        </Button>
        <Button type="button" onClick={onDone}>
          Cancel
        </Button>
      </span>
    </form>
  )
}

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
  const [extra, setExtra] = useState('')
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
        <legend>Goals, hours of usable integration</legend>
        {Object.keys(goals).map((f) => (
          <label key={f}>
            {f}{' '}
            <input
              className={`${v.input} ${p.num}`}
              type="number"
              min={0}
              max={1000}
              step={0.5}
              inputMode="decimal"
              placeholder="h"
              value={goals[f]}
              onChange={(e) => setGoals({ ...goals, [f]: e.target.value })}
            />
          </label>
        ))}
        <span className={v.actions}>
          <input
            className={`${v.input} ${p.num}`}
            aria-label="Another filter"
            placeholder="Filter"
            value={extra}
            onChange={(e) => setExtra(e.target.value)}
          />
          <Button
            type="button"
            disabled={!extra.trim() || extra.trim() in goals}
            onClick={() => {
              setGoals({ ...goals, [extra.trim()]: '' })
              setExtra('')
            }}
          >
            Add
          </Button>
        </span>
      </fieldset>
      <span className={v.actions}>
        <Button variant="primary" type="submit">
          Save
        </Button>
        <Button type="button" onClick={onDone}>
          Cancel
        </Button>
      </span>
    </form>
  )
}

/** Delete, asking first: what it unlinks, or why it can't go. */
function DeleteRow({ project: x, act, onDone }: { project: ProjectT; act: Act; onDone: () => void }) {
  const impact = useImpact(x.id)
  const i = impact.data
  return (
    <div className={p.form}>
      {!i ? (
        <span className="muted">Checking…</span>
      ) : i.combined.length ? (
        <span>
          Can't delete: it has combined masters ({i.combined.join(', ')}). Merge it into another project
          instead.
        </span>
      ) : (
        <ConfirmButton
          question={
            <>
              Delete {x.label}? {plural(i.datasets, 'dataset')} stay in the collection
              {i.finished.length ? `; no longer linked to ${i.finished.join(', ')}` : ''}.
            </>
          }
          confirm="Delete"
          onConfirm={() => {
            act.remove.mutate({ id: x.id, label: x.label })
            onDone()
          }}
        >
          Delete {x.label}…
        </ConfirmButton>
      )}
      <Button onClick={onDone}>Cancel</Button>
    </div>
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
        <label className={p.field}>
          Project{' '}
          <select className={v.select} value={into} onChange={(e) => setInto(Number(e.target.value))}>
            {others.map((o) => (
              <option key={o.id} value={o.id}>
                {o.label}
              </option>
            ))}
          </select>
        </label>
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
  const [by, setBy] = useState<'rig' | 'panel' | 'datasets'>(x.rigs.length > 1 ? 'rig' : 'panel')
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
        <span className={v.pills} role="group" aria-label="Split by">
          {(
            [
              ['rig', `By rig (${x.rigs.length})`],
              ['panel', `By panel (${x.panels.length})`],
              ['datasets', 'Chosen datasets'],
            ] as const
          ).map(([k, text]) => (
            <button key={k} type="button" aria-pressed={by === k} className={v.pill} onClick={() => setBy(k)}>
              {text}
            </button>
          ))}
        </span>
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
            <label className={p.field}>
              Name{' '}
              <input
                className={v.input}
                placeholder="Optional"
                value={name}
                onChange={(e) => setName(e.target.value)}
              />
            </label>
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
