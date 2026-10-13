// Metadata, path patterns and reconciliation (spec 001 US3).
import {
  useMutation,
  useQuery,
  useQueryClient,
  useInfiniteQuery,
  type QueryClient,
  type QueryKey,
} from '@tanstack/react-query'
import { api, unwrap } from '../../api/client'
import { optimistic, patchItems, type Patch } from '../../api/optimistic'
import type { components } from '../../api/schema'

export type ReconItem = components['schemas']['ReconciliationOut']
export type PathPattern = components['schemas']['PathPatternOut']
export type Preview = components['schemas']['PreviewOut']

/** Fields a user (or a pattern) can set, with how they're shown. */
export const FIELDS: { field: string; label: string; numeric?: boolean }[] = [
  { field: 'target', label: 'Target' },
  { field: 'panel', label: 'Panel', numeric: true },
  { field: 'object', label: 'Object (target and panel)' },
  { field: 'filter', label: 'Filter' },
  { field: 'exptime', label: 'Exposure (s)', numeric: true },
  { field: 'ccd_temp', label: 'Sensor temperature (°C)', numeric: true },
  { field: 'set_temp', label: 'Set temperature (°C)', numeric: true },
  { field: 'gain', label: 'Gain', numeric: true },
  { field: 'offset', label: 'Offset', numeric: true },
  { field: 'xbin', label: 'Binning X', numeric: true },
  { field: 'ybin', label: 'Binning Y', numeric: true },
  { field: 'camera', label: 'Camera' },
  { field: 'telescope', label: 'Telescope' },
  { field: 'date_obs', label: 'Observation time (UTC)' },
  { field: 'frame_type', label: 'Frame type' },
]
export const FIELD_LABEL = Object.fromEntries(FIELDS.map((f) => [f.field, f.label]))

export const FRAME_TYPES = [
  ['light', 'Light'],
  ['flat', 'Flat'],
  ['dark', 'Dark'],
  ['dark_flat', 'Dark flat'],
  ['bias', 'Bias'],
  ['master_dark', 'Master dark'],
  ['master_flat', 'Master flat'],
  ['master_bias', 'Master bias'],
  ['master_dark_flat', 'Master dark flat'],
] as const

/** Every query that shows resolved values; refreshed after any correction. */
const CATALOGUE: QueryKey[] = [
  ['datasets'],
  ['dataset'],
  ['frames'],
  ['frame'],
  ['reconciliation'],
  ['recon-counts'],
]

/** A row the server hasn't confirmed yet carries a temporary negative id (shown muted, "saving…"). */
let provisional = 0
export const tempId = () => --provisional

export function useReconciliation(status: 'open' | 'resolved' | 'dismissed' = 'open') {
  return useQuery({
    queryKey: ['reconciliation', status],
    queryFn: async () => unwrap(await api.GET('/reconciliation', { params: { query: { status } } })),
  })
}

export function useReconCounts() {
  return useQuery({
    queryKey: ['recon-counts'],
    queryFn: async () => unwrap(await api.GET('/reconciliation/counts')) as Record<string, number>,
    refetchInterval: 60_000,
  })
}

/** Drop answered items from the open list, and from the counts by kind, at once. */
function hideRecon(qc: QueryClient, ids: number[]): Patch[] {
  const gone: Record<string, number> = {}
  for (const x of qc.getQueryData<ReconItem[]>(['reconciliation', 'open']) ?? [])
    if (ids.includes(x.id)) gone[x.kind] = (gone[x.kind] ?? 0) + 1
  return [
    [
      ['reconciliation', 'open'],
      (old) =>
        patchItems<ReconItem>(
          old,
          (x) => ids.includes(x.id),
          () => null,
        ),
    ],
    [
      ['recon-counts'],
      (old) =>
        old &&
        Object.fromEntries(
          Object.entries(old as Record<string, number>).map(([k, n]) => [k, Math.max(0, n - (gone[k] ?? 0))]),
        ),
    ],
  ]
}

/** Answer items, one request each in order. `hide` is what leaves the list (the whole group when the answer
 * applies to similar files). */
export function useResolve() {
  const qc = useQueryClient()
  return useMutation({
    mutationKey: ['reconcile'],
    mutationFn: async (v: {
      ids: number[]
      hide?: number[]
      value?: string | number | null
      accept_suggestion?: boolean
      apply_to_similar?: boolean
    }) => {
      const { ids, hide: _hide, ...body } = v
      for (const id of ids)
        unwrap(
          await api.POST('/reconciliation/{id}/resolve', {
            params: { path: { id } },
            body: { accept_suggestion: false, apply_to_similar: false, ...body },
          }),
        )
    },
    ...optimistic(
      qc,
      (v) => hideRecon(qc, v.hide ?? v.ids),
      () => CATALOGUE,
    ),
    meta: { failed: "Couldn't save the answer" },
  })
}

export function useDismiss() {
  const qc = useQueryClient()
  return useMutation({
    mutationKey: ['reconcile'],
    mutationFn: async (ids: number[]) => {
      for (const id of ids)
        unwrap(await api.POST('/reconciliation/{id}/dismiss', { params: { path: { id } } }))
    },
    ...optimistic(
      qc,
      (ids: number[]) => hideRecon(qc, ids),
      () => CATALOGUE,
    ),
    meta: { failed: "Couldn't dismiss it" },
  })
}

type Meta = components['schemas']['MetadataFieldOut']
type FrameOut = components['schemas']['FrameOut']

/** A frame with one value set by you (or, for null, your value dropped so the next source wins). */
function withValue(f: FrameOut, field: string, value: string | number | null): FrameOut {
  const others = f.metadata.filter((m) => !(m.field === field && m.source === 'user'))
  let metadata: Meta[]
  if (value === null) {
    const next = others.find((m) => m.field === field)
    metadata = others.map((m) => (m === next ? { ...m, is_winner: true } : m))
  } else {
    const mine: Meta = {
      field,
      value: String(value),
      raw: null,
      source: 'user',
      source_detail: null,
      set_by: 'you',
      at: new Date().toISOString(),
      is_winner: true,
    }
    metadata = [...others.map((m) => (m.field === field ? { ...m, is_winner: false } : m)), mine]
  }
  return {
    ...f,
    metadata,
    ...(field === 'frame_type' && value !== null ? { frame_type: String(value) } : {}),
  }
}

/** `scope` makes repeated corrections to one sub run in order. */
export function useSetMetadata(scope?: string) {
  const qc = useQueryClient()
  return useMutation({
    scope: scope ? { id: scope } : undefined,
    mutationFn: async (body: { sha256s: string[]; field: string; value: string | number | null }) =>
      field_is_type(body.field)
        ? unwrap(
            await api.POST('/frames/classification', {
              body: { sha256s: body.sha256s, frame_type: String(body.value) },
            }),
          )
        : unwrap(await api.POST('/frames/metadata', { body })),
    ...optimistic(
      qc,
      (b) =>
        b.sha256s.map((sha): Patch => [
          ['frame', sha],
          (old) => (old ? withValue(old as FrameOut, b.field, b.value) : old),
        ]),
      () => CATALOGUE,
    ),
    meta: { failed: "Couldn't save the value" },
  })
}

function field_is_type(field: string) {
  return field === 'frame_type'
}

export function usePatterns() {
  return useQuery({
    queryKey: ['path-patterns'],
    queryFn: async () => unwrap(await api.GET('/path-patterns')),
  })
}

type PatternIn = Omit<PathPattern, 'id' | 'fields' | 'error'>

export function useSavePattern() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (p: PatternIn & { id?: number }) => {
      const { id, ...body } = p
      return id === undefined
        ? unwrap(await api.POST('/path-patterns', { body: body as PathPattern }))
        : unwrap(
            await api.PATCH('/path-patterns/{id}', { params: { path: { id } }, body: body as PathPattern }),
          )
    },
    // values are re-resolved in the background; live events refresh the rest
    ...optimistic(qc, (p) => [
      [
        ['path-patterns'],
        (old) => {
          if (p.id === undefined) {
            const row: PathPattern = { ...p, id: tempId(), fields: [], error: null }
            return old ? [...(old as PathPattern[]), row] : old
          }
          return patchItems<PathPattern>(
            old,
            (x) => x.id === p.id,
            (x) => ({ ...x, ...p }),
          )
        },
      ],
    ]),
    meta: { failed: "Couldn't save the pattern" },
  })
}

export function useDeletePattern() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (id: number) => {
      const res = await api.DELETE('/path-patterns/{id}', { params: { path: { id } } })
      if (!res.response.ok) unwrap(res)
    },
    ...optimistic(qc, (id: number) => [
      [
        ['path-patterns'],
        (old) =>
          patchItems<PathPattern>(
            old,
            (x) => x.id === id,
            () => null,
          ),
      ],
    ]),
    meta: { failed: "Couldn't delete the pattern" },
  })
}

export async function previewPattern(pattern: PatternIn, sample_paths: string[] = []): Promise<Preview> {
  return unwrap(
    await api.POST('/path-patterns/preview', { body: { pattern: pattern as PathPattern, sample_paths } }),
  )
}

// ---- ignore rules (US5) ----------------------------------------------------------------------------------
export type IgnoreRule = components['schemas']['IgnoreRuleOut']

const RULE_PAGE = 40

/** Ignore rules a page at a time (counting each rule's files is slow on the server). */
export function useIgnoreRules(sort: 'newest' | 'kind' | 'files') {
  return useInfiniteQuery({
    queryKey: ['ignore-rules', sort],
    initialPageParam: 0,
    queryFn: async ({ pageParam }) =>
      unwrap(
        await api.GET('/ignore-rules', { params: { query: { limit: RULE_PAGE, offset: pageParam, sort } } }),
      ),
    getNextPageParam: (last, all) => (last.length < RULE_PAGE ? undefined : all.length * RULE_PAGE),
  })
}

type IgnoreIn = {
  kind: 'folder' | 'glob' | 'content'
  value: string
  library_id?: number | null
  note?: string
}

type AddIgnore = { rules: IgnoreIn[]; sha256s?: string[]; recon?: number[] }

/** Add ignore rules (one or many, sent in order). Each shows at the top of the list at once, `sha256s` names
 * subs to show as ignored straight away (the sub it was ignored from, say), and `recon` reconciliation items
 * that leave the list with them. */
export function useAddIgnore() {
  const qc = useQueryClient()
  return useMutation({
    mutationKey: ['ignore'],
    mutationFn: async ({ rules }: AddIgnore) => {
      for (const rule of rules) unwrap(await api.POST('/ignore-rules', { body: rule as IgnoreRule }))
    },
    ...optimistic(
      qc,
      ({ rules, sha256s = [], recon = [] }: AddIgnore): Patch[] => [
        ...(recon.length ? hideRecon(qc, recon) : []),
        [
          ['ignore-rules'],
          (old) => {
            const inf = old as { pages: IgnoreRule[][] } | undefined
            if (!inf?.pages?.length) return old
            const rows: IgnoreRule[] = rules.map((r) => ({
              ...r,
              id: tempId(),
              active: true,
              created_at: new Date().toISOString(),
              created_by: 'you',
              matches: 0,
            }))
            return { ...inf, pages: [[...rows, ...inf.pages[0]], ...inf.pages.slice(1)] }
          },
        ],
        ...sha256s.map((sha): Patch => [
          ['frame', sha],
          (old) => (old ? { ...(old as FrameOut), status: 'ignored' } : old),
        ]),
      ],
      () => CATALOGUE,
    ),
    meta: { failed: "Couldn't ignore that" },
  })
}

export function useUndoIgnore() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (id: number) => {
      const res = await api.DELETE('/ignore-rules/{id}', { params: { path: { id } } })
      if (!res.response.ok) unwrap(res)
    },
    ...optimistic(
      qc,
      (id: number) => [
        [
          ['ignore-rules'],
          (old) =>
            patchItems<IgnoreRule>(
              old,
              (x) => x.id === id,
              () => null,
            ),
        ],
      ],
      () => CATALOGUE,
    ),
    meta: { failed: "Couldn't undo the ignore" },
  })
}
