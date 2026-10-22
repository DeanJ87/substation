// Projects inside a collection (006-DR-20, -24, amendment 2026-10-22): the object is the collection; a project is one
// season of shooting it ("2026", "2025–26 · widefield"). The hooks here read and change them; every change says
// what it did with Undo (spec 016).
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, unwrap } from '../../api/client'
import { optimistic } from '../../api/optimistic'
import { toast } from '../../components/Toasts'
import { offerUndo } from '../changes/changes'
import { deletedText } from '../changes/putAway'

export type ProjectT = NonNullable<ReturnType<typeof useProjects>['data']>['projects'][number]
export type ReviewT = NonNullable<ReturnType<typeof useProjects>['data']>['review'][number]

export function useProjects(collectionId: number) {
  return useQuery({
    queryKey: ['projects', collectionId],
    queryFn: async () =>
      unwrap(await api.GET('/collections/{id}/projects', { params: { path: { id: collectionId } } })),
  })
}

/** What merging (into `into`), splitting or removing a project would touch. */
export function useImpact(id: number, into: number | null = null, enabled = true) {
  return useQuery({
    queryKey: ['project-impact', id, into],
    enabled,
    queryFn: async () =>
      unwrap(
        await api.GET('/projects/{id}/impact', {
          params: { path: { id }, query: into ? { into } : {} },
        }),
      ),
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
    return { ...o, projects, unassigned: [...new Set(was)].filter((x) => !held.has(x)) }
  }

type Changed = { change_id?: number | null; warnings?: string[] }

export type PatchVars = {
  id: number
  name?: string
  season?: string
  kind?: 'auto' | 'single' | 'mosaic'
  planned_panels?: number | null
  goals?: Record<string, number | null>
  done?: boolean
  needs_review?: boolean
}

export function useProjectActions(collectionId: number) {
  const qc = useQueryClient()
  const key = ['projects', collectionId]
  const refresh = () => [['framing', collectionId], ['collection', collectionId], ['project-impact']]
  // every project edit in this collection runs in click order, each showing at once
  const scope = { id: `projects-${collectionId}` }
  const edit = <V,>(change: (vars: V) => (ps: ProjectT[]) => ProjectT[]) =>
    optimistic<V>(qc, (vars) => [[key, editProjects(change(vars))]], refresh)
  const settle = optimistic<unknown>(
    qc,
    () => [],
    () => [key, ...refresh()],
  )
  /** Say what happened, with Undo, and any warnings. */
  const said =
    <R extends Changed, V>(text: (r: R, vars: V) => string) =>
    (r: R, vars: V) => {
      offerUndo(qc, text(r, vars), r.change_id)
      for (const w of r.warnings ?? []) toast(w)
    }
  return {
    sort: useMutation({
      mutationFn: async () =>
        unwrap(
          await api.POST('/collections/{id}/projects/suggest', { params: { path: { id: collectionId } } }),
        ),
      scope,
      meta: { failed: "Couldn't sort into seasons" },
      ...settle,
      onSuccess: said((r) => {
        const made = r.created.length
        return `Sorted ${r.placed} dataset${r.placed === 1 ? '' : 's'} into seasons${made ? ` · ${made} new project${made === 1 ? '' : 's'}` : ''}`
      }),
    }),
    create: useMutation({
      mutationFn: async ({ season, name }: { season: string; name: string }) =>
        unwrap(
          await api.POST('/collections/{id}/projects', {
            params: { path: { id: collectionId } },
            body: { season, name, dataset_ids: [] },
          }),
        ),
      scope,
      meta: { failed: "Couldn't add the project" },
      // a provisional card until the server gives it an id
      ...edit(({ season, name }: { season: string; name: string }) => (ps) => [
        ...ps,
        {
          id: -Date.now(),
          name: [season, name].filter(Boolean).join(' · ') || 'Project',
          label: [season, name].filter(Boolean).join(' · ') || 'Project',
          own_name: name,
          season,
          kind: 'single',
          kind_auto: 'single',
          kind_override: null,
          planned_panels: null,
          panels: [],
          missing_panels: [],
          dataset_ids: [],
          accepted_integration_s: 0,
          first_night: null,
          last_night: null,
          position: ps.length,
          goals: {},
          filter_time: {},
          rigs: [],
          done: false,
          needs_review: false,
          review_reason: '',
          warnings: [],
        },
      ]),
      onSuccess: said((r) => `Added ${r.label}`),
    }),
    patch: useMutation({
      mutationFn: async ({ id, ...body }: PatchVars) =>
        unwrap(await api.PATCH('/projects/{id}', { params: { path: { id } }, body })),
      scope,
      meta: { failed: "Couldn't save the project" },
      ...edit(
        ({ id, goals, done, name, kind, ...body }: PatchVars) =>
          (ps) =>
            ps.map((p) =>
              p.id === id
                ? {
                    ...p,
                    ...body,
                    ...(name !== undefined ? { own_name: name } : {}),
                    ...(kind !== undefined
                      ? {
                          kind_override: kind === 'auto' ? null : kind,
                          kind: kind === 'auto' ? p.kind_auto : kind,
                        }
                      : {}),
                    ...(done !== undefined ? { done } : {}),
                    ...(goals
                      ? {
                          goals: Object.fromEntries(
                            Object.entries({ ...p.goals, ...goals }).filter(
                              (e): e is [string, number] => !!e[1],
                            ),
                          ),
                        }
                      : {}),
                  }
                : p,
            ),
      ),
      onSuccess: said((r, vars: PatchVars) =>
        vars.done !== undefined
          ? `${vars.done ? 'Marked' : 'Reopened'} ${r.label}${vars.done ? ' done' : ''}`
          : vars.needs_review === false
            ? `${r.label} kept apart`
            : `Saved ${r.label}`,
      ),
    }),
    remove: useMutation({
      mutationFn: async ({ id }: { id: number; label: string }) =>
        unwrap(await api.DELETE('/projects/{id}', { params: { path: { id } } })),
      scope,
      meta: { failed: "Couldn't delete the project" },
      ...edit(
        ({ id }: { id: number; label: string }) =>
          (ps) =>
            ps.filter((p) => p.id !== id),
      ),
      onSuccess: said((_r, vars: { id: number; label: string }) => deletedText('project', vars.label)),
    }),
    setDatasets: useMutation({
      mutationFn: async ({ id, ids }: { id: number; ids: number[] }) =>
        unwrap(await api.PUT('/projects/{id}/datasets', { params: { path: { id } }, body: { ids } })),
      scope,
      meta: { failed: "Couldn't move the dataset" },
      // a dataset moved in leaves whichever project held it
      ...edit(
        ({ id, ids }: { id: number; ids: number[] }) =>
          (ps) =>
            ps.map((p) =>
              p.id === id
                ? { ...p, dataset_ids: ids }
                : { ...p, dataset_ids: p.dataset_ids.filter((x) => !ids.includes(x)) },
            ),
      ),
      onSuccess: said((r) => `Moved datasets in ${r.label}`),
    }),
    merge: useMutation({
      mutationFn: async ({ into, from }: { into: number; from: number[] }) =>
        unwrap(
          await api.POST('/collections/{id}/projects/merge', {
            params: { path: { id: collectionId } },
            body: { into, from },
          }),
        ),
      scope,
      meta: { failed: "Couldn't merge" },
      ...settle,
      onSuccess: said((r, vars: { into: number; from: number[] }) => {
        const n = vars.from.length
        return `Merged ${n} project${n === 1 ? '' : 's'} into ${r.project.label}`
      }),
    }),
    split: useMutation({
      mutationFn: async ({
        id,
        ...body
      }: {
        id: number
        by: 'rig' | 'panel' | 'datasets'
        dataset_ids: number[]
        name: string
      }) => unwrap(await api.POST('/projects/{id}/split', { params: { path: { id } }, body })),
      scope,
      meta: { failed: "Couldn't split" },
      ...settle,
      onSuccess: said((r) => `Split ${r.project.label}: ${r.created.map((c) => c.label).join(', ')}`),
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

/** Delete a combined master (006-DR-38): its output file goes for good, so there's no Undo. Refused while it runs. */
export function useDeleteCombined() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async ({ id }: { id: number; name: string }) =>
      unwrap(
        await api.DELETE('/combined/{id}', { params: { path: { id } } }).then((r) => ({ ...r, data: null })),
      ),
    meta: { failed: "Couldn't delete the combined master" },
    onSuccess: (_r, vars) => toast(`Deleted ${vars.name}`),
    onSettled: () => {
      void qc.invalidateQueries({ queryKey: ['combined'] })
      void qc.invalidateQueries({ queryKey: ['project-impact'] })
      void qc.invalidateQueries({ queryKey: ['collection-impact'] })
    },
  })
}
