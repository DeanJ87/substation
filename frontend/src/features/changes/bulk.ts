// Bulk actions beyond subs (spec 016 U6): build several calibration sets, re-grade, stack or move several
// datasets, retry or dismiss several failed jobs. Moving and dismissing come back with Undo in the toast.
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { api, unwrap } from '../../api/client'
import { toast } from '../../components/Toasts'
import { offerUndo } from './changes'

const many = (n: number, one: string, more = `${one}s`) =>
  `${n.toLocaleString('en-GB')} ${n === 1 ? one : more}`

/** Skipped items, said once: "2 skipped: Already building." */
function skippedNote(skipped: { reason: string }[]) {
  if (!skipped.length) return ''
  const reasons = [...new Set(skipped.map((x) => x.reason))]
  return ` · ${skipped.length} skipped: ${reasons.slice(0, 2).join(' ')}${reasons.length > 2 ? ' …' : ''}`
}

export function useBulkBuild() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (ids: number[]) =>
      unwrap(await api.POST('/bulk/calibration-sets/build', { body: { ids, force: false } })),
    onSuccess: (r) => toast(`Queued ${many(r.queued, 'build')}${skippedNote(r.skipped)}`),
    onSettled: () => void qc.invalidateQueries(),
    meta: { failed: "Couldn't queue the builds" },
  })
}

/** Use, leave out, or clear your choice on several calibration frames; the toast offers Undo. */
export function useBulkOverride() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (body: { sha256s: string[]; verdict: 'pass' | 'reject' | null }) =>
      unwrap(await api.POST('/calibration-qa/override', { body })),
    onSuccess: (r, b) =>
      offerUndo(
        qc,
        r.queued
          ? `${b.verdict === 'pass' ? 'Using' : b.verdict === 'reject' ? 'Leaving out' : 'Cleared your choice on'} ${many(r.queued, 'frame')}`
          : 'Nothing to change',
        r.change_id,
      ),
    onSettled: () => void qc.invalidateQueries(),
    meta: { failed: "Couldn't save that" },
  })
}

export function useBulkDatasets() {
  const qc = useQueryClient()
  const refresh = () => void qc.invalidateQueries()
  return {
    regrade: useMutation({
      mutationFn: async (dataset_ids: number[]) =>
        unwrap(await api.POST('/bulk/datasets/regrade', { body: { dataset_ids } })),
      onSuccess: (r) => toast(`Re-grading ${many(r.queued, 'dataset')}; your own verdicts stay`),
      onSettled: refresh,
      meta: { failed: "Couldn't start the re-grade" },
    }),
    stack: useMutation({
      mutationFn: async (dataset_ids: number[]) =>
        unwrap(await api.POST('/bulk/datasets/stack', { body: { dataset_ids } })),
      onSuccess: (r) =>
        toast(`Started ${many(r.started, 'master')}${skippedNote(r.skipped)}`, r.started === 0),
      onSettled: refresh,
      meta: { failed: "Couldn't start the masters" },
    }),
    move: useMutation({
      mutationFn: async (body: { dataset_ids: number[]; collection_id: number | null; name?: string }) =>
        unwrap(
          await api.POST('/bulk/datasets/move', {
            body: { dataset_ids: body.dataset_ids, collection_id: body.collection_id },
          }),
        ),
      onSuccess: (r, body) =>
        offerUndo(
          qc,
          r.moved
            ? body.collection_id
              ? `Moved ${many(r.moved, 'dataset')} to ${body.name ?? 'the collection'}`
              : `Took ${many(r.moved, 'dataset')} out of their collection`
            : 'Already there',
          r.change_id,
        ),
      onSettled: refresh,
      meta: { failed: "Couldn't move the datasets" },
    }),
  }
}

export function useBulkJobs() {
  const qc = useQueryClient()
  const refresh = () => void qc.invalidateQueries({ queryKey: ['activity'] })
  return {
    retry: useMutation({
      mutationFn: async (ids: string[]) => unwrap(await api.POST('/work/bulk/jobs/retry', { body: { ids } })),
      onSuccess: (r) => toast(`Retrying ${many(r.done, 'job')}`),
      onSettled: refresh,
      meta: { failed: "Couldn't retry the jobs" },
    }),
    dismiss: useMutation({
      mutationFn: async (ids: string[]) =>
        unwrap(await api.POST('/work/bulk/jobs/dismiss', { body: { ids } })),
      onSuccess: (r) => {
        offerUndo(qc, `Dismissed ${many(r.done, 'failed job')}`, r.change_id)
        void qc.invalidateQueries({ queryKey: ['changes'] })
      },
      onSettled: refresh,
      meta: { failed: "Couldn't dismiss the jobs" },
    }),
  }
}
