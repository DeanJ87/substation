// API hooks for the v2 screens (specs 002–006). Live events refresh them.
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { optimistic, patchDeep, patchItems } from '../../api/optimistic'
import { toast } from '../../components/Toasts'
import { offerUndo } from '../changes/changes'
import { useRef } from 'react'
import { api, unwrap } from '../../api/client'
import { scopeQuery, type Scope } from '../scope/scope'
import { useLiveEvents } from '../../api/events'
import type { components } from '../../api/schema'

type S = components['schemas']
export type Sub = S['SubOut']
export type Session = S['SessionOut']
export type Stack = S['StackOut']
export type Job = S['JobOut']
type ActivityData = S['ActivityOut']
export type WorkerT = S['WorkerOut']
export type LibDataset = S['LibDatasetOut']
export type Card = S['CollectionCard']
export type DatasetT = S['DatasetOut']

const KEYS = [
  'library',
  'collection',
  'dataset',
  'datasets',
  'subs',
  'sessions',
  'stacks',
  'review',
  'review-count',
  'processing',
  'activity',
  'recon-counts',
  'calibration-sets',
  'masters',
  'calibration-set',
] as const

/** Batched refresh on server events, so a burst of subs is one refetch. */
export function useLiveRefresh(extra: string[] = []) {
  const qc = useQueryClient()
  const timer = useRef<number | null>(null)
  const schedule = () => {
    if (timer.current !== null) return
    timer.current = window.setTimeout(() => {
      timer.current = null
      for (const k of [...KEYS, ...extra]) void qc.invalidateQueries({ queryKey: [k] })
    }, 900)
  }
  useLiveEvents({
    'frame.catalogued': schedule,
    'frame.updated': schedule,
    'dataset.updated': schedule,
    'master.updated': schedule,
    'calibration.updated': schedule,
  })
}

/** The Library, narrowed on the server by the shared scope (spec 018); the last answer stays up while the next
 * one comes, so changing a filter doesn't blank the page. */
export function useLibrary(scope: Scope = {}) {
  const query = scopeQuery(scope)
  return useQuery({
    queryKey: ['library', query],
    queryFn: () => fetchLibrary(query),
    placeholderData: (prev) => prev,
  })
}
export function useCollection(id: number) {
  return useQuery({
    queryKey: ['collection', id],
    queryFn: async () => unwrap(await api.GET('/collections/{id}', { params: { path: { id } } })),
  })
}
export function useDatasetV2(id: number) {
  return useQuery({
    queryKey: ['dataset', id],
    queryFn: async () => unwrap(await api.GET('/datasets/{id}', { params: { path: { id } } })),
  })
}
export function useSubs(id: number) {
  return useQuery({
    queryKey: ['subs', id],
    queryFn: async () => unwrap(await api.GET('/datasets/{id}/subs', { params: { path: { id } } })),
  })
}
export function useSessions(id: number) {
  return useQuery({
    queryKey: ['sessions', id],
    queryFn: async () => unwrap(await api.GET('/datasets/{id}/sessions', { params: { path: { id } } })),
  })
}
export function useStacks(id: number) {
  return useQuery({
    queryKey: ['stacks', id],
    queryFn: async () => unwrap(await api.GET('/datasets/{id}/stacks', { params: { path: { id } } })),
    refetchInterval: (q) =>
      (q.state.data ?? []).some((m) => m.state === 'running' || m.state === 'queued') ? 3000 : false,
  })
}
export function useProcessing(sha: string | null) {
  return useQuery({
    queryKey: ['processing', sha],
    enabled: !!sha,
    queryFn: async () =>
      unwrap(await api.GET('/frames/{sha256}/processing', { params: { path: { sha256: sha! } } })),
  })
}
export function useReview() {
  return useQuery({ queryKey: ['review'], queryFn: async () => unwrap(await api.GET('/review')) })
}
export function useReviewCount() {
  return useQuery({
    queryKey: ['review-count'],
    queryFn: async () => unwrap(await api.GET('/review/count')),
    refetchInterval: 60_000,
  })
}
export function useActivity(enabled = true) {
  return useQuery({
    queryKey: ['activity'],
    enabled,
    queryFn: async () => unwrap(await api.GET('/work')),
    refetchInterval: 2000,
  })
}

function useInvalidateAll() {
  const qc = useQueryClient()
  return () => {
    for (const k of KEYS) void qc.invalidateQueries({ queryKey: [k] })
  }
}

const VERDICT_SHOWN = { accept: 'accept', keep: 'down', reject: 'reject' } as const
type VerdictBody = { sha256s: string[]; verdict: 'accept' | 'keep' | 'reject' | 'auto' }

/** A verdict shows at once wherever the sub appears (review, dataset subs, the sub page); the server's
 * recount of the dataset follows. */
export function useVerdict() {
  const qc = useQueryClient()
  const refresh = useInvalidateAll()
  const subPatch = (b: VerdictBody) => (old: unknown) =>
    patchDeep(
      old,
      (x) => typeof x.sha256 === 'string' && 'verdict' in x && b.sha256s.includes(x.sha256),
      (x) =>
        b.verdict === 'auto'
          ? { ...x, verdict: x.machine_verdict ?? x.verdict, manual: false }
          : { ...x, verdict: VERDICT_SHOWN[b.verdict], manual: true },
    )
  return useMutation({
    mutationFn: async (body: VerdictBody) => unwrap(await api.POST('/frames/verdict', { body })),
    meta: { failed: "Couldn't save the verdict" },
    // spec 016: a change to several subs offers Undo (one sub has its own keys: U reverts it)
    onSuccess: (r, b) => {
      if (r.updated > 1) offerUndo(qc, verdictText(b.verdict, r.updated), r.change_id)
    },
    // the same subs judged again wait for the previous answer, so the last click wins
    scope: { id: 'verdict' },
    ...optimistic<VerdictBody>(qc, (b) => [
      [['subs'], subPatch(b)],
      [['review'], subPatch(b)],
      [['processing'], subPatch(b)],
    ]),
    onSettled: refresh,
  })
}
export function useStartStack(id: number) {
  const qc = useQueryClient()
  const refresh = useInvalidateAll()
  return useMutation({
    mutationFn: async (body: {
      rule: 'default' | 'accepted' | 'graded' | 'everything'
      nights?: string[] | null
      date_from?: string | null
      date_to?: string | null
      datasets?: number[] | null
      include?: string[] | null
      exclude?: string[] | null
      options?: {
        rejection?: 'winsorized' | 'sigma' | 'linear' | null
        weighting?: 'grade' | 'snr' | 'equal' | null
        reference?: 'best_fwhm' | 'most_stars' | null
      } | null
    }) => unwrap(await api.POST('/datasets/{id}/stacks', { params: { path: { id } }, body })),
    meta: { failed: "Couldn't start the stack" },
    onMutate: async (body) => {
      // a waiting version appears at once; the real one replaces it when the server answers
      await qc.cancelQueries({ queryKey: ['stacks', id] })
      qc.setQueryData<S['StackOut'][]>(['stacks', id], (old) => {
        if (!old) return old
        const version = Math.max(0, ...old.map((m) => m.version)) + 1
        // every field filled: the first master of a dataset has no earlier version to copy from, and the
        // version card maps over steps and nights (2026-10-11: "can't access property map" on a first stack)
        const stub: S['StackOut'] = {
          id: -version,
          version,
          dataset_id: id,
          state: 'queued',
          state_reason: '',
          file_path: '',
          step: '',
          steps: old[0]?.steps ?? [],
          progress: 0,
          error: null,
          has_preview: false,
          created_at: new Date().toISOString(),
          created_by: null,
          started_at: null,
          finished_at: null,
          engine_version: '',
          method: old[0]?.method ?? '',
          rule: body.rule,
          rule_text: '',
          nights: body.nights ?? [],
          report: {},
          integration_s: 0,
          session_count: body.nights?.length ?? 0,
          sub_count: 0,
        }
        return [stub, ...old]
      })
    },
    onSettled: refresh,
  })
}
type StackAct = { id: number; action: 'rerun' | 'cancel' | 'delete' }
export function useStackAction() {
  const qc = useQueryClient()
  const refresh = useInvalidateAll()
  return useMutation({
    meta: { failed: "Couldn't change the stack" },
    scope: { id: 'stack-action' },
    ...optimistic<StackAct>(qc, ({ id, action }) => [
      [
        ['stacks'],
        (old) =>
          patchItems<S['StackOut']>(
            old,
            (m) => m.id === id,
            (m) =>
              action === 'delete'
                ? null
                : action === 'cancel'
                  ? { ...m, state: 'cancelled' }
                  : { ...m, state: 'queued', error: null, progress: 0 },
          ),
      ],
    ]),
    mutationFn: async ({ id, action }: { id: number; action: 'rerun' | 'cancel' | 'delete' }) => {
      if (action === 'delete') {
        const r = await api.DELETE('/stacks/{id}', { params: { path: { id } } })
        if (!r.response.ok) unwrap(r)
        return null
      }
      return action === 'rerun'
        ? unwrap(await api.POST('/stacks/{id}/rerun', { params: { path: { id } } }))
        : unwrap(await api.POST('/stacks/{id}/cancel', { params: { path: { id } } }))
    },
    onSettled: refresh,
  })
}
type LibraryHome = Awaited<ReturnType<typeof fetchLibrary>>
const fetchLibrary = async (query: Record<string, string | number> = {}) =>
  unwrap(await api.GET('/library', { params: { query } }))

export function useCollectionActions() {
  const qc = useQueryClient()
  const refresh = useInvalidateAll()
  // the row leaves the ungrouped list at once; the library catches up in the background
  const hide = ({ dataset_ids }: { dataset_ids: number[] }) => {
    void qc.cancelQueries({ queryKey: ['library'] })
    qc.setQueriesData<LibraryHome>(
      { queryKey: ['library'] },
      (d) => d && { ...d, ungrouped: d.ungrouped.filter((u) => !dataset_ids.includes(u.dataset.id)) },
    )
  }
  return {
    create: useMutation({
      mutationFn: async (body: { name: string; dataset_ids: number[] }) =>
        unwrap(await api.POST('/collections', { body })),
      onMutate: hide,
      onSettled: refresh,
      meta: { failed: "Couldn't create the collection" },
    }),
    add: useMutation({
      mutationFn: async ({ id, dataset_ids }: { id: number; dataset_ids: number[] }) =>
        unwrap(
          await api.POST('/collections/{id}/datasets', { params: { path: { id } }, body: { dataset_ids } }),
        ),
      onMutate: hide,
      onSettled: refresh,
      meta: { failed: "Couldn't add to the collection" },
    }),
    acceptAll: useMutation({
      mutationFn: async () => unwrap(await api.POST('/collections/accept-suggestions')),
      meta: { failed: "Couldn't accept the suggestions" },
      // suggested rows leave at once
      onMutate: () => {
        void qc.cancelQueries({ queryKey: ['library'] })
        qc.setQueriesData<LibraryHome>(
          { queryKey: ['library'] },
          (d) =>
            d && { ...d, ungrouped: d.ungrouped.filter((u) => !(u as { suggestion?: unknown }).suggestion) },
        )
      },
      onSettled: refresh,
    }),
  }
}
type JobAct = { id: string; action: 'retry' | 'cancel' | 'bump' | 'dismiss' }
/** Job buttons act at once: a cancelled or bumped job leaves its place, a dismissed failure goes, a retried one
 * leaves the failures; Activity's next poll shows where it really is. */
export function useJobAction() {
  const qc = useQueryClient()
  const drop = (id: string) => (old: unknown) =>
    patchItems<Job>(
      old,
      (j) => j.id === id,
      () => null,
    )
  return useMutation({
    meta: { failed: "Couldn't change the job" },
    scope: { id: 'job-action' },
    ...optimistic<JobAct>(qc, ({ id, action }) => [
      [
        ['activity'],
        (old) => {
          const d = old as ActivityData | undefined
          if (!d || !('queue' in d)) return drop(id)(old)
          if (action === 'cancel')
            return {
              ...d,
              queue: d.queue.filter((j) => j.id !== id),
              running: d.running.map((j) => (j.id === id ? { ...j, note: 'Cancelling…' } : j)),
            }
          if (action === 'bump') {
            const j = d.queue.find((x) => x.id === id)
            return j ? { ...d, queue: [j, ...d.queue.filter((x) => x.id !== id)] } : d
          }
          return { ...d, failed: d.failed.filter((j) => j.id !== id) }
        },
      ],
      // the paged queue
      [
        ['activity', 'queue'],
        (old) => {
          if (action === 'cancel') return drop(id)(old)
          if (action !== 'bump') return old
          const inf = old as { pages: Job[][] } | undefined
          const j = inf?.pages.flat().find((x) => x.id === id)
          if (!inf || !j) return old
          const pages = inf.pages.map((p) => p.filter((x) => x.id !== id))
          pages[0] = [j, ...(pages[0] ?? [])]
          return { ...inf, pages }
        },
      ],
    ]),
    mutationFn: async ({ id, action }: JobAct) => {
      const path = { params: { path: { id } } }
      if (action === 'retry') return unwrap(await api.POST('/work/jobs/{id}/retry', path))
      if (action === 'cancel') return unwrap(await api.POST('/work/jobs/{id}/cancel', path))
      if (action === 'bump') return unwrap(await api.POST('/work/jobs/{id}/bump', path))
      return unwrap(await api.POST('/work/jobs/{id}/dismiss', path))
    },
  })
}
/** Place a waiting job just before or after another (005 T008). */
type MoveJob = { id: string; before?: string; after?: string }
const moveIn = (list: Job[], { id, before, after }: MoveJob): Job[] => {
  const j = list.find((x) => x.id === id)
  if (!j) return list
  const rest = list.filter((x) => x.id !== id)
  const at = rest.findIndex((x) => x.id === (before ?? after))
  if (at < 0) return list
  rest.splice(before ? at : at + 1, 0, j)
  return rest
}
export function useMoveJob() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async ({ id, before, after }: MoveJob) =>
      unwrap(await api.POST('/work/jobs/{id}/move', { params: { path: { id } }, body: { before, after } })),
    meta: { failed: "Couldn't move the job" },
    scope: { id: 'job-move' },
    ...optimistic<MoveJob>(qc, (m) => [
      [
        ['activity', 'queue'],
        (old) => {
          const inf = old as { pages: Job[][]; pageParams: unknown[] } | undefined
          if (!inf?.pages) return old
          // reorder across the loaded pages, then cut back into pages of the same sizes
          const sizes = inf.pages.map((p) => p.length)
          const all = moveIn(inf.pages.flat(), m)
          const pages = sizes.map((n, i) =>
            all.slice(sizes.slice(0, i).reduce((a, b) => a + b, 0)).slice(0, n),
          )
          return { ...inf, pages }
        },
      ],
    ]),
  })
}
export function usePause() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (paused: boolean) => unwrap(await api.POST('/work/pause', { body: { paused } })),
    meta: { failed: "Couldn't change pause" },
    scope: { id: 'pause' },
    ...optimistic<boolean>(qc, (paused) => [
      [['activity'], (old) => (old && typeof old === 'object' && 'paused' in old ? { ...old, paused } : old)],
    ]),
  })
}

export const previewUrl = (sha: string, size: 'thumb' | 'screen' = 'thumb') =>
  `/api/v1/frames/${sha}/preview?size=${size}`
export const stackPreviewUrl = (id: number, size: 'thumb' | 'screen' = 'thumb') =>
  `/api/v1/stacks/${id}/preview?size=${size}`

export function fwhmText(s: { fwhm_arcsec?: number | null; fwhm_px?: number | null }): string {
  if (s.fwhm_arcsec) return `${s.fwhm_arcsec.toFixed(2)}″`
  if (s.fwhm_px) return `${s.fwhm_px.toFixed(2)} px`
  return '—'
}
export const num = (n: number | null | undefined, digits = 0) =>
  n == null
    ? '—'
    : n.toLocaleString('en-GB', { maximumFractionDigits: digits, minimumFractionDigits: digits })

export type SetDetail = S['SetDetailOut']
export type Built = S['BuiltOut']
export function useCalibrationSet(id: number) {
  return useQuery({
    queryKey: ['calibration-set', id],
    queryFn: async () => unwrap(await api.GET('/calibration-sets/{id}/detail', { params: { path: { id } } })),
  })
}
type Override = { sha256s: string[]; verdict: 'pass' | 'reject' | null }
export function useCalibrationActions() {
  const qc = useQueryClient()
  const refresh = useInvalidateAll()
  // a build shows as queued at once on the set's page and in the library list
  const queued = (id: number) => (old: unknown) =>
    patchDeep(
      old,
      (x) => x.id === id && 'frame_count' in x,
      (x) => ({
        ...x,
        built_state: 'queued',
        builds: [{ id: -1, state: 'queued' }, ...((x.builds as []) ?? [])],
      }),
    )
  return {
    qa: useMutation({
      mutationFn: async (id: number) =>
        unwrap(await api.POST('/calibration-sets/{id}/qa', { params: { path: { id } } })),
      meta: { failed: "Couldn't start the check" },
      scope: { id: 'calibration-qa' },
      onMutate: () => toast('Checking the frames…'),
      onSettled: refresh,
    }),
    build: useMutation({
      mutationFn: async ({ id, force = false }: { id: number; force?: boolean }) =>
        unwrap(await api.POST('/calibration-sets/{id}/build', { params: { path: { id } }, body: { force } })),
      meta: { failed: "Couldn't start the build" },
      scope: { id: 'calibration-build' },
      ...optimistic<{ id: number }>(qc, ({ id }) => [
        [['calibration-set', id], queued(id)],
        [['calibration-sets'], queued(id)],
      ]),
      onSettled: refresh,
    }),
    buildMissing: useMutation({
      mutationFn: async () => unwrap(await api.POST('/calibration-sets/build-missing')),
      meta: { failed: "Couldn't queue the builds" },
      scope: { id: 'calibration-build' },
      onMutate: () => toast('Queueing missing masters…'),
      onSettled: refresh,
    }),
    override: useMutation({
      mutationFn: async (body: Override) => unwrap(await api.POST('/calibration-qa/override', { body })),
      meta: { failed: "Couldn't save that" },
      // Reject then Undo on the same frame run in order, so the last click wins
      scope: { id: 'calibration-override' },
      ...optimistic<Override>(qc, (b) => [
        [
          ['calibration-set'],
          (old) =>
            patchDeep(
              old,
              (x) => typeof x.sha256 === 'string' && 'override' in x && b.sha256s.includes(x.sha256),
              (x) => ({ ...x, override: b.verdict }),
            ),
        ],
      ]),
      onSettled: refresh,
    }),
  }
}
export const qaThumbUrl = (sha: string) => `/api/v1/calibration-qa/${sha}/thumb`
export const builtPreviewUrl = (id: number, kind: 'screen' | 'thumb' | 'motes' | 'cmp' = 'screen') =>
  `/api/v1/built-masters/${id}/preview?kind=${kind}`

const VERDICT_DONE = {
  accept: 'Accepted',
  keep: 'Down-weighted',
  reject: 'Rejected',
  auto: 'Cleared overrides on',
}
export function verdictText(verdict: keyof typeof VERDICT_DONE, n: number) {
  return `${VERDICT_DONE[verdict]} ${n.toLocaleString('en-GB')} subs`
}
