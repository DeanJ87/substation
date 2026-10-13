// Settings draft (spec 008, 008-DR-04): edits collect here until Save. The save bar names each change, and a
// grading change previews how many datasets would be re-graded before "Save and re-grade".
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useBlocker } from '@tanstack/react-router'
import { createContext, useContext, useMemo, useState, type ReactNode } from 'react'
import { api, unwrap } from '../../api/client'
import { optimistic } from '../../api/optimistic'
import type { components } from '../../api/schema'
import { Button } from '../../components/ui'
import s from './settings.module.css'

export type Processing = {
  calibration: { temp_tolerance_c: number; later_flat_fallback: boolean; weak_flat_days: number | null }
  grading: {
    profile: string
    fwhm: [number, number]
    stars: [number, number]
    background: [number, number]
    eccentricity: [number, number]
    min_session: number
    version: number
    use_conditions: boolean
  }
  stacking: {
    rejection: string
    sigma: [number, number]
    weighting: string
    reference: string
    auto: string
    auto_quiet_hours: number
    auto_every_n: number
    format: string
  }
  notifications: { ntfy: string; webhook: string; events: string[] }
  queue: { priority_mode: string }
  paths: { map: { from: string; to: string }[] }
  bin: { auto_bin_rejected_days: number; purge_after_days: number }
  post: {
    enabled: boolean
    steps: PostStep[]
    gpu: boolean
    graxpert: string
    rc_astro: string
    timeout_s: number
  }
}
/** One finishing step (spec 010); the parameters depend on the step. */
export type PostStep = { step: string; enabled: boolean; [param: string]: string | number | boolean }
type Path = [keyof Processing, string]
type Change = { path: Path; label: string; from: string; to: string }

const LABELS: Record<string, string> = {
  'grading.fwhm': 'FWHM',
  'grading.stars': 'Star count',
  'grading.background': 'Background',
  'grading.eccentricity': 'Eccentricity',
  'grading.min_session': 'Minimum subs for a final grade',
  'grading.profile': 'Grader',
  'grading.use_conditions': 'Use SQM and cloud when recorded',
  'calibration.temp_tolerance_c': 'Dark temperature tolerance',
  'calibration.later_flat_fallback': 'Use a later flat when none is earlier',
  'stacking.rejection': 'Rejection',
  'stacking.sigma': 'Sigma',
  'stacking.weighting': 'Weighting',
  'stacking.reference': 'Registration reference',
  'stacking.auto': 'Auto-stack',
  'queue.priority_mode': 'Work order',
  'stacking.auto_quiet_hours': 'Quiet time after a session',
  'stacking.auto_every_n': 'New subs per automatic master',
  'stacking.format': 'Output',
  'paths.map': 'File paths',
  'bin.auto_bin_rejected_days': 'Bin rejected subs after (days)',
  'bin.purge_after_days': 'Delete binned files after (days)',
  'post.enabled': 'Post-process new masters',
  'post.steps': 'Post-processing steps',
  'post.gpu': 'Use the GPU',
  'notifications.ntfy': 'ntfy topic',
  'notifications.webhook': 'Webhook',
  'notifications.events': 'Notify about',
}

export function fmt(v: unknown): string {
  if (Array.isArray(v)) return v.map((x) => fmt(x)).join(' / ')
  if (typeof v === 'boolean') return v ? 'on' : 'off'
  if (typeof v === 'number') return Number.isInteger(v) ? String(v) : v.toFixed(2)
  return String(v ?? '—')
}

type Ctx = {
  saved: Processing | null
  draft: Processing | null
  set: (section: keyof Processing, key: string, value: unknown) => void
  changes: Change[]
  readOnly: boolean
}
const DraftCtx = createContext<Ctx>({ saved: null, draft: null, set: () => {}, changes: [], readOnly: true })
export const useDraft = () => useContext(DraftCtx)

export function useSettings() {
  return useQuery({ queryKey: ['settings'], queryFn: async () => unwrap(await api.GET('/settings')) })
}

type SettingsPatch = Omit<components['schemas']['SettingsIn'], 'regrade' | 'processing'>

/** Save top-level settings (site, workers) outside the draft: shown as saved at once, rolled back on failure. */
export function useSaveSettings(failed: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (body: SettingsPatch) =>
      unwrap(await api.PATCH('/settings', { body: { ...body, regrade: false } })),
    ...optimistic(qc, (body: SettingsPatch) => [
      [['settings'], (old) => old && { ...(old as object), ...body }],
    ]),
    meta: { failed },
  })
}

export function DraftProvider({ children, readOnly }: { children: ReactNode; readOnly: boolean }) {
  const q = useSettings()
  const saved = (q.data?.processing as Processing | undefined) ?? null
  const [edits, setEdits] = useState<Record<string, unknown>>({})
  const draft = useMemo(() => {
    if (!saved) return null
    const d = structuredClone(saved) as Record<string, Record<string, unknown>>
    for (const [k, v] of Object.entries(edits)) {
      const [sec, key] = k.split('.')
      d[sec][key] = v
    }
    return d as unknown as Processing
  }, [saved, edits])
  const changes = useMemo(() => {
    if (!saved) return []
    return Object.entries(edits)
      .map(([k, v]) => {
        const [sec, key] = k.split('.') as Path
        const was = (saved[sec] as Record<string, unknown>)[key]
        return { path: [sec, key] as Path, label: LABELS[k] ?? key, from: fmt(was), to: fmt(v) }
      })
      .filter((c) => c.from !== c.to)
  }, [saved, edits])
  // Save makes the draft the saved settings at once; the server confirms (or it rolls back with a note, and the
  // edits are still here to try again). Only edits still as they were when saved are cleared.
  const qc = useQueryClient()
  const save = useMutation({
    mutationFn: async ({ body, regrade }: { body: Body; regrade: boolean }) =>
      unwrap(await api.PATCH('/settings', { body: { processing: body, regrade } })),
    ...optimistic(qc, ({ body }: { body: Body; regrade: boolean }) => [
      [
        ['settings'],
        (old) => {
          const o = old as { processing: Record<string, Record<string, unknown>> } | undefined
          if (!o) return old
          const processing = { ...o.processing }
          for (const [sec, vals] of Object.entries(body)) processing[sec] = { ...processing[sec], ...vals }
          return { ...o, processing }
        },
      ],
    ]),
    onSuccess: (_d, { body }) =>
      setEdits((e) =>
        Object.fromEntries(
          Object.entries(e).filter(([k, v]) => {
            const [sec, key] = k.split('.')
            return body[sec]?.[key] !== v
          }),
        ),
      ),
    meta: { failed: "Couldn't save the settings" },
  })
  const value = {
    saved,
    draft,
    readOnly,
    changes,
    set: (section: keyof Processing, key: string, v: unknown) =>
      setEdits((e) => ({ ...e, [`${section}.${key}`]: v })),
  }
  // leaving with unsaved changes asks here, in the page (spec 008 edge case), not in a browser dialog
  const blocker = useBlocker({ shouldBlockFn: () => changes.length > 0, withResolver: true })
  return (
    <DraftCtx.Provider value={value}>
      {children}
      {blocker.status === 'blocked' && (
        <div className={s.saveBar} role="alertdialog" aria-label="Unsaved settings">
          <strong>
            Leave without saving? {changes.length} change{changes.length === 1 ? '' : 's'} will be lost.
          </strong>
          <div className={s.rowActions}>
            <Button variant="danger" onClick={() => blocker.proceed()}>
              Leave
            </Button>
            <Button onClick={() => blocker.reset()}>Stay</Button>
          </div>
        </div>
      )}
      {changes.length > 0 && !readOnly && blocker.status !== 'blocked' && (
        <SaveBar
          changes={changes}
          draft={draft!}
          onSave={(body, regrade) => save.mutate({ body, regrade })}
          onDone={() => setEdits({})}
        />
      )}
      {changes.length === 0 && save.isPending && (
        <div className={s.saveBar} role="status">
          <strong>Saving…</strong>
        </div>
      )}
    </DraftCtx.Provider>
  )
}

type Body = Record<string, Record<string, unknown>>

function SaveBar({
  changes,
  draft,
  onSave,
  onDone,
}: {
  changes: Change[]
  draft: Processing
  onSave: (body: Body, regrade: boolean) => void
  onDone: () => void
}) {
  const body = useMemo(() => {
    const out: Body = {}
    for (const c of changes) {
      out[c.path[0]] ??= {}
      out[c.path[0]][c.path[1]] = (draft[c.path[0]] as Record<string, unknown>)[c.path[1]]
    }
    return out
  }, [changes, draft])
  const grading = 'grading' in body
  const preview = useQuery({
    queryKey: ['settings-preview', body],
    enabled: grading,
    queryFn: async () => unwrap(await api.POST('/settings/preview', { body: { processing: body } })),
  })
  const n = preview.data?.length ?? 0
  const subs = (preview.data ?? []).reduce((a, r) => a + r.changes, 0)
  return (
    <div className={s.saveBar} role="region" aria-label="Unsaved settings">
      <div>
        <strong>
          {changes.length} unsaved change{changes.length === 1 ? '' : 's'}
        </strong>
        <div className={s.saveDetail}>
          {changes.map((c) => `${c.label} ${c.from} → ${c.to}`).join(' · ')}
          {grading &&
            (preview.isPending
              ? ' · checking what would be re-graded…'
              : ` · ${n} dataset${n === 1 ? '' : 's'} would be re-graded (${subs} verdict${subs === 1 ? '' : 's'} change). Manual overrides are kept.`)}
        </div>
        {preview.error && <div className={s.error}>{preview.error.message}</div>}
      </div>
      <div className={s.rowActions}>
        <Button onClick={onDone}>Discard</Button>
        {grading && n > 0 && (
          <Button variant="primary" onClick={() => onSave(body, true)}>
            Save and re-grade
          </Button>
        )}
        <Button variant={grading && n > 0 ? 'default' : 'primary'} onClick={() => onSave(body, false)}>
          Save
        </Button>
      </div>
    </div>
  )
}
