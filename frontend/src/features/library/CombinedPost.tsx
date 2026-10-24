// Post-processing a stitched mosaic or a stacked-together master (spec 010 US6, 2026-10-24): the same chain and
// stages as a dataset's master. It runs by itself after combining when post-processing is on; an admin can run it
// (again) from the card. Each finished stage opens the 100% view on its version.
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { api, unwrap } from '../../api/client'
import { Zoomable } from '../../components/CloseLook'
import { FilePath } from '../../components/FilePath'
import { Button } from '../../components/ui'
import { dateTimeText, durationText } from '../format'
import { useCanEdit } from '../settings/draft'
import { PostRunDialog } from '../post/PostRunDialog'
import v from '../v2/v2.module.css'
import c from './collection.module.css'

/** A combined master's post-processing runs, newest first; polled while one is queued or running. */
export function useCombinedPost(id: number, enabled = true) {
  return useQuery({
    queryKey: ['post-combined', id],
    enabled,
    queryFn: async () => unwrap(await api.GET('/combined/{id}/post', { params: { path: { id } } })),
    refetchInterval: (query) => (query.state.data?.queued ? 5000 : false),
  })
}

/** The latest processed stage with a preview, to show on the card in place of the original. */
export function useProcessedPreview(id: number, enabled = true) {
  const q = useCombinedPost(id, enabled)
  return [...(q.data?.runs[0]?.stages ?? [])].reverse().find((st) => st.state === 'done' && st.preview)
}

export function CombinedPost({ id, name }: { id: number; name: string }) {
  const qc = useQueryClient()
  const admin = useCanEdit()
  const q = useCombinedPost(id)
  const [choosing, setChoosing] = useState(false)
  const start = useMutation({
    // exactly the steps chosen for this run, with Settings' parameters (010-DR-29)
    mutationFn: async (steps: string[]) =>
      unwrap(await api.POST('/combined/{id}/post', { params: { path: { id } }, body: { steps } })),
    scope: { id: `post-combined-${id}` },
    meta: { failed: "Couldn't start post-processing" },
    onMutate: () =>
      qc.setQueryData(['post-combined', id], (o: object | undefined) => (o ? { ...o, queued: true } : o)),
    onSettled: () => qc.invalidateQueries({ queryKey: ['post-combined', id] }),
  })
  const d = q.data
  if (!d) return null
  const run = d.runs[0]
  if (!run && !d.queued && !admin) return null
  return (
    <div className={c.post}>
      <div className={v.actions}>
        <strong>Post-processing</strong>
        <span className={v.muted}>
          {d.queued
            ? d.helper_online
              ? `queued on ${d.helper_host}`
              : `queued · starts when a post-processing helper connects${
                  d.helper_seen_at ? ` (${d.helper_host} last seen ${dateTimeText(d.helper_seen_at)})` : ''
                }`
            : run
              ? `run ${run.run} · ${dateTimeText(run.finished_at)}${run.helper ? ` on ${run.helper}` : ''}`
              : 'not run yet'}
        </span>
        {admin && (
          <Button
            size="sm"
            variant="ghost"
            disabled={d.queued || start.isPending}
            onClick={() => setChoosing(true)}
            title="Choose the steps, then run them from the untouched file"
          >
            {run ? 'Run again…' : 'Run post-processing…'}
          </Button>
        )}
      </div>
      {run?.chosen && (
        <span className={v.muted}>
          Steps chosen for this run: {run.chosen.length ? stepNames(run) : 'none'}
        </span>
      )}
      {run && (
        <ol className={c.postStages}>
          {run.stages.map((st, i) => (
            <li key={i} className={st.state === 'done' ? undefined : v.muted}>
              {st.state === 'done' && (st.preview || st.full) && (
                // a thumbnail per finished stage; it opens the 100% view on that version, tabs for the others
                <Zoomable
                  target={{ kind: 'combined', id }}
                  name={`${name} · ${st.label}`}
                  version={st.step === 'trim' ? undefined : st.step}
                  className={c.postThumb}
                >
                  {st.preview ? (
                    <img src={`${st.preview}?size=thumb`} alt={`${name}, ${st.label}`} loading="lazy" />
                  ) : (
                    <span>View at 100%</span>
                  )}
                </Zoomable>
              )}
              <span className={c.postText}>
                <strong>{st.label}</strong>
                <span className={v.note}>
                  {st.state !== 'done'
                    ? st.reason
                    : st.step === 'trim'
                      ? 'registration border removed'
                      : `${st.tool_label || 'GraXpert'} · ${durationText(st.seconds ?? 0)}`}
                </span>
              </span>
            </li>
          ))}
        </ol>
      )}
      {run && run.stages.some((st) => st.file_path) && (
        // each version's linear 32-bit file, out of the way of the pictures
        <details className={c.postFiles}>
          <summary className={v.muted}>Files of each step</summary>
          <ul>
            {run.stages
              .filter((st) => st.file_path)
              .map((st) => (
                <li key={st.step}>
                  <span className={v.muted}>{st.label}</span>
                  <FilePath path={st.file_path ?? ''} download={st.download} />
                </li>
              ))}
          </ul>
        </details>
      )}
      {choosing && (
        <PostRunDialog
          name={name}
          steps={d.steps ?? []}
          again={!!run}
          onRun={(steps) => start.mutate(steps)}
          onClose={() => setChoosing(false)}
        />
      )}
    </div>
  )
}

type Run = NonNullable<ReturnType<typeof useCombinedPost>['data']>['runs'][number]
/** "Background extracted, Deconvolved": the steps a run was asked for, by the names its stages carry. */
export function stepNames(run: Run) {
  return (run.chosen ?? []).map((k) => run.stages.find((st) => st.step === k)?.label ?? k).join(', ')
}

/** The card's picture: the latest processed version when there is one (as a dataset master's card), else the
 * combined master itself. Either opens the 100% view, on that version. */
export function CombinedThumb({ id, name, current }: { id: number; name: string; current: boolean }) {
  const processed = useProcessedPreview(id, current)
  return (
    <Zoomable target={{ kind: 'combined', id }} name={name} version={processed?.step}>
      <img
        src={processed ? `${processed.preview}?size=thumb` : `/api/v1/combined/${id}/preview?size=thumb`}
        alt={processed ? `${name}, ${processed.label}` : name}
        loading="lazy"
      />
    </Zoomable>
  )
}
