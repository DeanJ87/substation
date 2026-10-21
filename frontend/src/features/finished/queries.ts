// Finished projects (spec 020): the owner's hand-finished work in a Completed library, linked to the SubStation
// projects whose subs made it, with file roles and processing steps for the renderer.
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, unwrap } from '../../api/client'
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
}
/** One file each: choosing it for one file takes it from any other (as the server does). */
export const SINGLE_ROLES = new Set(['final', 'starless', 'stars'])

/** "Final", "Single filter: Hα", "Progressive stack 2" */
export function roleText(f: Pick<FinishedFile, 'role' | 'role_filter' | 'role_order'>): string {
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
    processing: useChange(
      id,
      async (steps: string[]) =>
        unwrap(await api.PUT('/finished/{id}/processing', { ...path, body: { steps } })),
      "Couldn't save the processing steps",
    ),
    projectJson: useChange(
      id,
      async () => unwrap(await api.POST('/finished/{id}/project-json', path)),
      "Couldn't write project.json",
    ),
  }
}
