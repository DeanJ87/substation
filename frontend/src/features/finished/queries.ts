// Finished projects (spec 020): the owner's hand-finished work in a Completed library, linked to the SubStation
// projects whose subs made it, with file roles (processing steps among them) and the distance for the renderer.
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, ApiError, unwrap } from '../../api/client'
import type { components } from '../../api/schema'

export type Finished = components['schemas']['FinishedOut']
export type FinishedFile = components['schemas']['FileOut']
export type RoleChange = components['schemas']['RoleIn']

export const KIND: Record<string, string> = { astro: 'Astro', nightscapes: 'Nightscapes', videos: 'Videos' }
export const ROLE: Record<string, string> = {
  '': 'None',
  final: 'Final',
  starless: 'Starless',
  stars: 'Stars only',
  per_filter: 'Single filter',
  progressive: 'Progressive stack',
  step: 'Processing step',
}
/** A file's picture from the server, scaled down (a JPEG): a thumbnail, or the larger preview. */
export const imageUrl = (id: number, fileId: number, size: 'thumb' | 'preview' = 'thumb') =>
  `/api/v1/finished/${id}/files/${fileId}/image?size=${size}`

/** One file each: choosing it for one file takes it from any other (as the server does). */
export const SINGLE_ROLES = new Set(['final', 'starless', 'stars'])

/** "Final", "Single filter: Hα", "Progressive stack 2", "Step 2 · GraXpert" */
export function roleText(
  f: Pick<FinishedFile, 'role' | 'role_filter' | 'role_order' | 'role_label'>,
): string {
  if (f.role === 'step')
    return `Step${f.role_order ? ` ${f.role_order}` : ''}${f.role_label ? ` · ${f.role_label}` : ''}`
  if (f.role === 'per_filter') return `${ROLE.per_filter}${f.role_filter ? `: ${f.role_filter}` : ''}`
  if (f.role === 'progressive') return `${ROLE.progressive}${f.role_order ? ` ${f.role_order}` : ''}`
  return ROLE[f.role] ?? f.role
}

const LIST = ['finished-list']

async function fetchList(rescan: boolean) {
  return unwrap(await api.GET('/finished', { params: { query: { rescan } } }))
}

export function useFinishedList() {
  return useQuery({ queryKey: LIST, queryFn: () => fetchList(false) })
}

/** Look at the Completed library again now, rather than within the next few minutes. */
export function useRescanFinished() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () => fetchList(true),
    onSuccess: (d) => qc.setQueryData(LIST, d),
    meta: { failed: "Couldn't rescan the Completed library" },
  })
}

export function useFinished(id: number) {
  return useQuery({
    queryKey: ['finished', id],
    queryFn: async () => unwrap(await api.GET('/finished/{id}', { params: { path: { id } } })),
  })
}

export function useSuggestions(id: number) {
  return useQuery({
    queryKey: ['finished', id, 'suggestions'],
    queryFn: async () => unwrap(await api.GET('/finished/{id}/suggestions', { params: { path: { id } } })),
  })
}

export function useRenderData(id: number) {
  return useQuery({
    queryKey: ['finished', id, 'render-data'],
    queryFn: async () => unwrap(await api.GET('/finished/{id}/render-data', { params: { path: { id } } })),
    retry: false,
  })
}

/** Every change answers with the whole project: it replaces what's shown, and the list and preview catch up. */
function useChange<V>(id: number, call: (v: V) => Promise<Finished>, failed: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: call,
    onSuccess: (d) => qc.setQueryData(['finished', id], d),
    onSettled: () => {
      void qc.invalidateQueries({ queryKey: LIST })
      void qc.invalidateQueries({ queryKey: ['finished', id, 'render-data'] })
    },
    meta: { failed },
  })
}

export function useFinishedActions(id: number) {
  const qc = useQueryClient()
  const path = { params: { path: { id } } }
  return {
    links: useChange(
      id,
      async (project_ids: number[]) =>
        unwrap(await api.PUT('/finished/{id}/links', { ...path, body: { project_ids } })),
      "Couldn't change the links",
    ),
    roles: useChange(
      id,
      async (roles: RoleChange[]) =>
        unwrap(await api.PUT('/finished/{id}/roles', { ...path, body: { roles } })),
      "Couldn't save the file roles",
    ),
    guess: useChange(
      id,
      async () => unwrap(await api.POST('/finished/{id}/roles/guess', path)),
      "Couldn't guess the roles",
    ),
    distance: useChange(
      id,
      async (distance_ly: number | null) =>
        unwrap(await api.PUT('/finished/{id}/distance', { ...path, body: { distance_ly } })),
      "Couldn't save the distance",
    ),
    // a refusal (set by hand, not found, SIMBAD unreachable) is an answer shown beside the field, not a failure toast
    lookup: useMutation({
      mutationFn: async (): Promise<{ project?: Finished; error?: string }> => {
        try {
          return { project: unwrap(await api.POST('/finished/{id}/distance/lookup', path)) }
        } catch (e) {
          if (e instanceof ApiError) return { error: e.message }
          throw e
        }
      },
      onSuccess: (r) => r.project && qc.setQueryData(['finished', id], r.project),
      meta: { failed: "Couldn't look up the distance" },
      onSettled: () => void qc.invalidateQueries({ queryKey: ['finished', id, 'render-data'] }),
    }),
  }
}

export type Progression = components['schemas']['ProgressionOut']
export type Checkpoint = components['schemas']['CheckpointOut']

/** Still being built: the page asks again every few seconds until it isn't. */
export const BUILDING = new Set(['queued', 'running'])

/** The cumulative stacks after each night (020-DR-15): polled while queued or running, still otherwise. */
export function useProgression(id: number) {
  return useQuery({
    queryKey: ['finished', id, 'progression'],
    queryFn: async () => unwrap(await api.GET('/finished/{id}/progression', { params: { path: { id } } })),
    refetchInterval: (q) => (BUILDING.has(q.state.data?.state ?? '') ? 3000 : false),
  })
}

/** Generate (or, with force, rebuild) them. The server's refusal (409, unavailable) is an answer shown beside the
 * button, not a failure toast. */
export function useGenerateProgression(id: number) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (force: boolean): Promise<{ progression?: Progression; error?: string }> => {
      try {
        return {
          progression: unwrap(
            await api.POST('/finished/{id}/progression', { params: { path: { id } }, body: { force } }),
          ),
        }
      } catch (e) {
        if (e instanceof ApiError && e.status === 409) return { error: e.message }
        throw e
      }
    },
    onSuccess: (r) => r.progression && qc.setQueryData(['finished', id, 'progression'], r.progression),
    meta: { failed: "Couldn't start the progression" },
  })
}
