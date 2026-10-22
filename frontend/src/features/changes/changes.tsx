// Changes made by hand, and undoing them (spec 016): a toast offers Undo after a bulk change, Ctrl/Cmd+Z undoes
// your latest change anywhere, and Activity lists your recent changes, each with Undo.
import {
  useInfiniteQuery,
  useMutation,
  useQuery,
  useQueryClient,
  type QueryClient,
} from '@tanstack/react-query'
import { useEffect } from 'react'
import { api, unwrap } from '../../api/client'
import { toast } from '../../components/Toasts'
import { countText } from '../format'

export async function undoChange(qc: QueryClient, id: number) {
  try {
    const r = unwrap(await api.POST('/changes/{id}/undo', { params: { path: { id } } }))
    toast(r.note)
  } catch (e) {
    toast(e instanceof Error ? e.message : "Couldn't undo that.", true)
  }
  await qc.invalidateQueries()
}

/** A toast saying what was done, with Undo when the change can be undone. */
export function offerUndo(qc: QueryClient, text: string, changeId: number | null | undefined) {
  toast(text, false, changeId ? { label: 'Undo', run: () => void undoChange(qc, changeId) } : undefined)
}

export const CHANGES_PAGE = 20

/** Your changes, newest first, a page at a time (More asks for the next 20 by offset). */
export function useChanges() {
  return useInfiniteQuery({
    queryKey: ['changes', 'all'],
    initialPageParam: 0,
    queryFn: async ({ pageParam }) =>
      unwrap(await api.GET('/changes', { params: { query: { limit: CHANGES_PAGE, offset: pageParam } } })),
    getNextPageParam: (last, pages) => (last.length < CHANGES_PAGE ? undefined : pages.length * CHANGES_PAGE),
  })
}

/** What you deleted (collections and projects), newest first: the two kinds asked for apart, then merged. */
export function useDeletedChanges(enabled: boolean) {
  return useQuery({
    queryKey: ['changes', 'deleted'],
    enabled,
    queryFn: async () => {
      const kinds = ['collection', 'project'] as const
      const lists = await Promise.all(
        kinds.map(async (kind) =>
          unwrap(await api.GET('/changes', { params: { query: { kind, limit: 100 } } })),
        ),
      )
      return lists
        .flat()
        .filter((c) => c.summary.startsWith('Deleted '))
        .sort((a, b) => b.created_at.localeCompare(a.created_at) || b.id - a.id)
    },
  })
}

export function useUndo() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (id: number) => undoChange(qc, id),
  })
}

/** Agree with the automatic grades of a dataset's flagged subs: a night's, or all of them. */
export function useAgree(datasetId: number) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (body: { night?: string; sha256s?: string[] }) =>
      unwrap(await api.POST('/frames/agree', { body: { dataset_id: datasetId, ...body } })),
    onSuccess: (r) =>
      offerUndo(
        qc,
        r.updated
          ? `Agreed with ${countText(r.updated)} grade${r.updated === 1 ? '' : 's'}`
          : 'Nothing left to agree with',
        r.change_id,
      ),
    onSettled: () => void qc.invalidateQueries(),
    meta: { failed: "Couldn't agree with the grades" },
  })
}

function typing(t: EventTarget | null) {
  return t instanceof HTMLElement && !!t.closest('input, select, textarea, [contenteditable="true"]')
}

/** Ctrl/Cmd+Z anywhere (outside a text field) undoes your latest change that can still be undone. */
export function UndoKeys() {
  const qc = useQueryClient()
  useEffect(() => {
    async function key(e: KeyboardEvent) {
      if (!(e.metaKey || e.ctrlKey) || e.shiftKey || e.altKey || e.key.toLowerCase() !== 'z') return
      if (typing(e.target)) return
      e.preventDefault()
      const r = await api.GET('/changes', { params: { query: { limit: 1 } } })
      const last = r.data?.[0]
      if (!last?.can_undo) {
        toast('Nothing to undo.')
        return
      }
      await undoChange(qc, last.id)
    }
    const handler = (e: KeyboardEvent) => void key(e)
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [qc])
  return null
}
