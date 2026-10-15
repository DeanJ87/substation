// Projects on a collection's Overview (006-DR-20, spec 019 amendment 2026-10-15): the collection is the object; a
// project is one way of shooting it (a rig, a single field or an N-panel mosaic, a season) with its own goals.
// Each card shows how far along it is per filter; "Show only this" narrows the page to it.
import { useState } from 'react'
import { Collapsible } from '../../components/Collapsible'
import { Button, ConfirmButton } from '../../components/ui'
import { integrationText, monthSpan } from '../format'
import v from '../v2/v2.module.css'
import s from './library.module.css'
import p from './projects.module.css'
import { type ProjectT, ProjectBoard, useProjectActions, useProjects } from './Projects'

type FilterTime = { total_s: number; accepted_s: number; rejected_s: number }
type Ds = { dataset: { id: number }; label: string }

/** Kept, waiting and goal for one filter, in seconds; pct when there's a goal. */
export function filterProgress(time: FilterTime | undefined, goalHours: number | undefined) {
  const kept = time?.accepted_s ?? 0
  const waiting = time ? Math.max(0, time.total_s - time.accepted_s - time.rejected_s) : 0
  const goal = (goalHours ?? 0) * 3600
  return { kept, waiting, goal, pct: goal ? Math.min(100, Math.round((kept / goal) * 100)) : null }
}

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
  const [name, setName] = useState('')
  const projects = q.data?.projects ?? []
  const unassigned = q.data?.unassigned ?? []
  return (
    <section className={`${v.card} ${v.cardPad}`}>
      <Collapsible
        id="collection-projects"
        title="Projects"
        meta={`${projects.length} project${projects.length === 1 ? '' : 's'}`}
      >
        <p className="muted">
          A project is one way of shooting this target (a rig, a single field or a mosaic), with its own
          goals.
        </p>
        <div className={p.cards}>
          {projects.map((x) => (
            <ProjectCard
              key={x.id}
              project={x}
              selected={value === x.id}
              onShow={() => onChange(value === x.id ? null : x.id)}
              act={act}
            />
          ))}
          {unassigned.length > 0 && (
            <article className={`${p.card} ${p.loose}`}>
              <strong>Not in a project</strong>
              <span className="muted">
                {unassigned.length} dataset{unassigned.length === 1 ? '' : 's'}
              </span>
              <div className={v.actions}>
                <Button onClick={() => act.suggest.mutate()} disabled={act.suggest.isPending}>
                  Suggest projects
                </Button>
                <Button onClick={() => setArranging(true)}>Put them in projects…</Button>
              </div>
            </article>
          )}
        </div>
        <div className={p.foot}>
          <form
            className={v.actions}
            onSubmit={(e) => {
              e.preventDefault()
              if (!name.trim()) return
              act.create.mutate(name.trim())
              setName('')
            }}
          >
            <input
              className={v.input}
              placeholder="New project, e.g. 20-panel mosaic 2027"
              value={name}
              aria-label="New project name"
              onChange={(e) => setName(e.target.value)}
            />
            <Button type="submit" disabled={!name.trim() || act.create.isPending}>
              Add project
            </Button>
          </form>
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
        </div>
        {arranging && <ProjectBoard collectionId={collectionId} datasets={datasets} />}
      </Collapsible>
    </section>
  )
}

function ProjectCard({
  project: x,
  selected,
  onShow,
  act,
}: {
  project: ProjectT
  selected: boolean
  onShow: () => void
  act: ReturnType<typeof useProjectActions>
}) {
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState<{
    name: string
    kind: string
    panels: string
    goals: Record<string, string>
  }>()
  const [extra, setExtra] = useState('')
  const filters = [...new Set([...Object.keys(x.filter_time ?? {}), ...Object.keys(x.goals ?? {})])].sort()
  const most = Math.max(1, ...filters.map((f) => x.filter_time?.[f]?.total_s ?? 0))
  const kind =
    x.kind === 'mosaic'
      ? `Mosaic · ${x.panels.length}${x.planned_panels ? ` of ${x.planned_panels}` : ''} panels${x.missing_panels.length ? ` · missing ${x.missing_panels.join(', ')}` : ''}`
      : 'Single field'
  const start = () => {
    setDraft({
      name: x.name,
      kind: x.kind,
      panels: x.planned_panels ? String(x.planned_panels) : '',
      goals: Object.fromEntries(filters.map((f) => [f, x.goals?.[f] ? String(x.goals[f]) : ''])),
    })
    setExtra('')
    setEditing(true)
  }
  const save = () => {
    if (!draft) return
    act.patch.mutate({
      id: x.id,
      name: draft.name.trim() || x.name,
      kind: draft.kind,
      planned_panels: draft.kind === 'mosaic' ? Number(draft.panels) || null : null,
      goals: Object.fromEntries(
        Object.entries(draft.goals).map(([f, h]) => [f, h.trim() ? Number(h) : null]),
      ),
    })
    setEditing(false)
  }
  return (
    <article className={`${p.card} ${selected ? p.selected : ''}`}>
      <header className={p.head}>
        <div>
          <strong>{x.name}</strong>
          <div className="muted">
            {[kind, x.rigs.join(', '), monthSpan(x.first_night, x.last_night)].filter(Boolean).join(' · ')}
          </div>
        </div>
        <span className={v.mono}>{integrationText(x.accepted_integration_s)}</span>
      </header>

      {!editing && filters.length > 0 && (
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

      {editing && draft && (
        <form
          className={p.form}
          onSubmit={(e) => {
            e.preventDefault()
            save()
          }}
        >
          <label>
            Name{' '}
            <input
              className={v.input}
              value={draft.name}
              onChange={(e) => setDraft({ ...draft, name: e.target.value })}
            />
          </label>
          <label>
            Kind{' '}
            <select
              className={v.select}
              value={draft.kind}
              onChange={(e) => setDraft({ ...draft, kind: e.target.value })}
            >
              <option value="single">Single field</option>
              <option value="mosaic">Mosaic</option>
            </select>
          </label>
          {draft.kind === 'mosaic' && (
            <label>
              Panels{' '}
              <input
                className={`${v.input} ${p.num}`}
                type="number"
                min={1}
                max={100}
                value={draft.panels}
                onChange={(e) => setDraft({ ...draft, panels: e.target.value })}
              />
            </label>
          )}
          <fieldset className={p.goals}>
            <legend>Goals (hours of usable integration)</legend>
            {Object.keys(draft.goals).map((f) => (
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
                  value={draft.goals[f]}
                  onChange={(e) => setDraft({ ...draft, goals: { ...draft.goals, [f]: e.target.value } })}
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
                disabled={!extra.trim() || extra.trim() in draft.goals}
                onClick={() => {
                  setDraft({ ...draft, goals: { ...draft.goals, [extra.trim()]: '' } })
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
            <Button type="button" onClick={() => setEditing(false)}>
              Cancel
            </Button>
            <ConfirmButton
              question={<>Remove this project? Its datasets stay in the collection.</>}
              confirm="Remove"
              onConfirm={() => act.remove.mutate(x.id)}
            >
              Remove
            </ConfirmButton>
          </span>
        </form>
      )}

      {!editing && (
        <div className={v.actions}>
          <button type="button" className={v.pill} aria-pressed={selected} onClick={onShow}>
            {selected ? 'Showing only this' : 'Show only this'}
          </button>
          <Button onClick={start}>{Object.keys(x.goals ?? {}).length ? 'Edit' : 'Edit · set goals'}</Button>
        </div>
      )}
    </article>
  )
}
