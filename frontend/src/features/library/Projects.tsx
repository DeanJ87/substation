// Projects inside a collection (006-DR-20, -24): the object is the collection; a project is one way of shooting it
// ("6-panel mosaic 2026", "Single panel 2025"). The bar picks the project the page shows; the board names projects,
// sets their kind and planned panels, and moves datasets between them by dragging (or Alt+↑/↓ and the menu).
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { api, unwrap } from '../../api/client'
import { optimistic } from '../../api/optimistic'
import { Button, ConfirmButton } from '../../components/ui'
import { integrationText } from '../format'
import v from '../v2/v2.module.css'
import c from './collection.module.css'

type ProjectT = NonNullable<ReturnType<typeof useProjects>['data']>['projects'][number]
type Ds = { dataset: { id: number }; label: string }

export function useProjects(collectionId: number) {
  return useQuery({
    queryKey: ['projects', collectionId],
    queryFn: async () =>
      unwrap(await api.GET('/collections/{id}/projects', { params: { path: { id: collectionId } } })),
  })
}

type ProjectsT = { projects: ProjectT[]; unassigned: number[] }

/** Apply `change` to the cached projects, then put any dataset no project holds back under "Not in a project". */
const editProjects =
  (change: (ps: ProjectT[]) => ProjectT[]) =>
  (old: unknown): unknown => {
    const o = old as ProjectsT | undefined
    if (!o) return old
    const projects = change(o.projects)
    const held = new Set(projects.flatMap((p) => p.dataset_ids))
    const was = [...o.unassigned, ...o.projects.flatMap((p) => p.dataset_ids)]
    return { projects, unassigned: [...new Set(was)].filter((x) => !held.has(x)) }
  }

function useProjectActions(collectionId: number) {
  const qc = useQueryClient()
  const key = ['projects', collectionId]
  const refresh = () => [['framing', collectionId]]
  // every project edit in this collection runs in click order, each showing at once
  const scope = { id: `projects-${collectionId}` }
  const edit = <V,>(change: (vars: V) => (ps: ProjectT[]) => ProjectT[]) =>
    optimistic<V>(qc, (vars) => [[key, editProjects(change(vars))]], refresh)
  return {
    suggest: useMutation({
      mutationFn: async () =>
        unwrap(
          await api.POST('/collections/{id}/projects/suggest', { params: { path: { id: collectionId } } }),
        ),
      scope,
      meta: { failed: "Couldn't suggest projects" },
      ...optimistic<void>(
        qc,
        () => [],
        () => [key, ...refresh()],
      ),
    }),
    create: useMutation({
      mutationFn: async (name: string) =>
        unwrap(
          await api.POST('/collections/{id}/projects', {
            params: { path: { id: collectionId } },
            body: { name, kind: 'single', dataset_ids: [] },
          }),
        ),
      scope,
      meta: { failed: "Couldn't add the project" },
      // a provisional card until the server gives it an id
      ...edit((name: string) => (ps) => [
        ...ps,
        {
          id: -Date.now(),
          name,
          kind: 'single',
          planned_panels: null,
          panels: [],
          missing_panels: [],
          dataset_ids: [],
          accepted_integration_s: 0,
          first_night: null,
          last_night: null,
          position: ps.length,
        },
      ]),
    }),
    patch: useMutation({
      mutationFn: async ({
        id,
        ...body
      }: {
        id: number
        name?: string
        kind?: string
        planned_panels?: number | null
      }) => unwrap(await api.PATCH('/projects/{id}', { params: { path: { id } }, body })),
      scope,
      meta: { failed: "Couldn't save the project" },
      ...edit(
        ({ id, ...body }: { id: number } & Partial<ProjectT>) =>
          (ps) =>
            ps.map((p) => (p.id === id ? { ...p, ...body } : p)),
      ),
    }),
    remove: useMutation({
      mutationFn: async (id: number) =>
        unwrap(await api.DELETE('/projects/{id}', { params: { path: { id } } })),
      scope,
      meta: { failed: "Couldn't remove the project" },
      ...edit((id: number) => (ps) => ps.filter((p) => p.id !== id)),
    }),
    setDatasets: useMutation({
      mutationFn: async ({ id, ids }: { id: number; ids: number[] }) =>
        unwrap(await api.PUT('/projects/{id}/datasets', { params: { path: { id } }, body: { ids } })),
      scope,
      meta: { failed: "Couldn't move the dataset" },
      ...edit(
        ({ id, ids }: { id: number; ids: number[] }) =>
          (ps) =>
            ps.map((p) => (p.id === id ? { ...p, dataset_ids: ids } : p)),
      ),
    }),
    order: useMutation({
      mutationFn: async (ids: number[]) =>
        unwrap(
          await api.PUT('/collections/{id}/projects/order', {
            params: { path: { id: collectionId } },
            body: { ids },
          }),
        ),
      scope,
      meta: { failed: "Couldn't reorder the projects" },
      ...edit((ids: number[]) => (ps) => [...ps].sort((a, b) => ids.indexOf(a.id) - ids.indexOf(b.id))),
    }),
  }
}

/** Which project the page shows: All, or one; drag the chips to reorder projects. */
export function ProjectBar({
  collectionId,
  value,
  onChange,
  onManage,
  managing,
}: {
  collectionId: number
  value: number | null
  onChange: (id: number | null) => void
  onManage: () => void
  managing: boolean
}) {
  const q = useProjects(collectionId)
  const act = useProjectActions(collectionId)
  const [dragged, setDragged] = useState<number | null>(null)
  const projects = q.data?.projects ?? []
  const move = (from: number, to: number) => {
    const ids = projects.map((p) => p.id)
    const [x] = ids.splice(from, 1)
    ids.splice(to, 0, x)
    act.order.mutate(ids)
  }
  return (
    <div className={c.projectBar} role="group" aria-label="Projects">
      <span className={v.sectionLabel}>Projects</span>
      <button type="button" className={v.pill} aria-pressed={value == null} onClick={() => onChange(null)}>
        All datasets
      </button>
      {projects.map((p, i) => (
        <button
          key={p.id}
          type="button"
          className={`${v.pill} ${dragged === p.id ? c.dragging : ''}`}
          aria-pressed={value === p.id}
          draggable
          title="Drag or Alt+←/→ to reorder"
          onDragStart={() => setDragged(p.id)}
          onDragEnd={() => setDragged(null)}
          onDragOver={(e) => e.preventDefault()}
          onDrop={() => {
            const from = projects.findIndex((x) => x.id === dragged)
            if (from >= 0 && from !== i) move(from, i)
            setDragged(null)
          }}
          onKeyDown={(e) => {
            if (!e.altKey) return
            if (e.key === 'ArrowLeft' && i > 0) move(i, i - 1)
            else if (e.key === 'ArrowRight' && i < projects.length - 1) move(i, i + 1)
          }}
          onClick={() => onChange(p.id)}
        >
          {p.name}
          {p.kind === 'mosaic' && p.planned_panels ? ` · ${p.panels.length}/${p.planned_panels}` : ''}
        </button>
      ))}
      {!projects.length && (q.data?.unassigned.length ?? 0) > 0 && (
        <Button onClick={() => act.suggest.mutate()} disabled={act.suggest.isPending}>
          Suggest projects
        </Button>
      )}
      <button type="button" className={v.pill} aria-pressed={managing} onClick={onManage}>
        Manage…
      </button>
    </div>
  )
}

/** Name projects, set kind and planned panels, and move datasets between them by dragging. */
export function ProjectBoard({ collectionId, datasets }: { collectionId: number; datasets: Ds[] }) {
  const q = useProjects(collectionId)
  const act = useProjectActions(collectionId)
  const [dragged, setDragged] = useState<{ ds: number; from: number | null } | null>(null)
  const [name, setName] = useState('')
  const label = new Map(datasets.map((d) => [d.dataset.id, d.label]))
  const projects = q.data?.projects ?? []
  const unassigned = q.data?.unassigned ?? []

  /** Put dataset `ds` into project `to` before dataset `before` (or at the end). */
  const place = (ds: number, to: number | null, before: number | null) => {
    const from = projects.find((p) => p.dataset_ids.includes(ds))
    if (from && from.id !== to)
      act.setDatasets.mutate({ id: from.id, ids: from.dataset_ids.filter((x) => x !== ds) })
    if (to == null) return
    const target = projects.find((p) => p.id === to)
    if (!target) return
    const ids = target.dataset_ids.filter((x) => x !== ds)
    const at = before == null ? ids.length : Math.max(0, ids.indexOf(before))
    ids.splice(at, 0, ds)
    act.setDatasets.mutate({ id: to, ids })
  }

  const column = (p: ProjectT | null) => {
    const ids = p ? p.dataset_ids : unassigned
    return (
      <div
        key={p?.id ?? 'none'}
        className={`${v.card} ${v.cardPad} ${c.projectCol}`}
        onDragOver={(e) => e.preventDefault()}
        onDrop={(e) => {
          e.preventDefault()
          if (dragged && (e.target as HTMLElement).closest('li') == null)
            place(dragged.ds, p?.id ?? null, null)
          setDragged(null)
        }}
      >
        {p ? (
          <>
            <input
              className={v.input}
              defaultValue={p.name}
              aria-label="Project name"
              onBlur={(e) =>
                e.target.value.trim() &&
                e.target.value !== p.name &&
                act.patch.mutate({ id: p.id, name: e.target.value })
              }
            />
            <div className={v.actions}>
              <select
                className={v.select}
                value={p.kind}
                aria-label="Kind"
                onChange={(e) => act.patch.mutate({ id: p.id, kind: e.target.value })}
              >
                <option value="single">Single field</option>
                <option value="mosaic">Mosaic</option>
              </select>
              {p.kind === 'mosaic' && (
                <input
                  className={v.input}
                  type="number"
                  min={1}
                  max={100}
                  style={{ width: 72 }}
                  defaultValue={p.planned_panels ?? ''}
                  aria-label="Planned panels"
                  onBlur={(e) =>
                    act.patch.mutate({ id: p.id, planned_panels: Number(e.target.value) || null })
                  }
                />
              )}
              <ConfirmButton
                className={v.pill}
                question={<>Remove this project? Its datasets stay in the collection.</>}
                confirm="Remove"
                onConfirm={() => act.remove.mutate(p.id)}
              >
                Remove
              </ConfirmButton>
            </div>
            <div className={v.muted}>
              {p.kind === 'mosaic'
                ? `${p.panels.length}${p.planned_panels ? ` of ${p.planned_panels}` : ''} panels${p.missing_panels.length ? ` · missing ${p.missing_panels.join(', ')}` : ''} · `
                : ''}
              {integrationText(p.accepted_integration_s)}
            </div>
          </>
        ) : (
          <strong>Not in a project</strong>
        )}
        <ul className={c.projectList}>
          {ids.map((ds, i) => (
            <li key={ds} className={dragged?.ds === ds ? c.dragging : undefined}>
              <button
                type="button"
                className={c.projectItem}
                onDragOver={(e) => e.preventDefault()}
                onDrop={(e) => {
                  e.preventDefault()
                  e.stopPropagation()
                  if (dragged && dragged.ds !== ds) place(dragged.ds, p?.id ?? null, ds)
                  setDragged(null)
                }}
                draggable
                title="Drag or Alt+↑/↓ to reorder"
                onDragStart={() => setDragged({ ds, from: p?.id ?? null })}
                onDragEnd={() => setDragged(null)}
                onKeyDown={(e) => {
                  if (!e.altKey || !p) return
                  const order = [...p.dataset_ids]
                  if (e.key === 'ArrowUp' && i > 0) [order[i - 1], order[i]] = [order[i], order[i - 1]]
                  else if (e.key === 'ArrowDown' && i < order.length - 1)
                    [order[i + 1], order[i]] = [order[i], order[i + 1]]
                  else return
                  e.preventDefault()
                  act.setDatasets.mutate({ id: p.id, ids: order })
                }}
              >
                {label.get(ds) ?? `Dataset ${ds}`}
              </button>
            </li>
          ))}
          {!ids.length && <li className={v.muted}>Drop datasets here</li>}
        </ul>
      </div>
    )
  }

  return (
    <div className={c.projectBoard}>
      <div className={v.actions}>
        <input
          className={v.input}
          placeholder="New project"
          value={name}
          aria-label="New project name"
          onChange={(e) => setName(e.target.value)}
        />
        <Button
          disabled={!name.trim() || act.create.isPending}
          onClick={() => (act.create.mutate(name.trim()), setName(''))}
        >
          Add project
        </Button>
        {unassigned.length > 0 && (
          <Button onClick={() => act.suggest.mutate()} disabled={act.suggest.isPending}>
            Suggest projects for {unassigned.length} dataset{unassigned.length === 1 ? '' : 's'}
          </Button>
        )}
      </div>
      <div className={c.projectCols}>
        {projects.map((p) => column(p))}
        {column(null)}
      </div>
    </div>
  )
}
