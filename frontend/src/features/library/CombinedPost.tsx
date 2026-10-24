// Post-processing a stitched mosaic or a stacked-together master (spec 010 US6, 2026-10-24): the same chain and
// stages as a dataset's master. It runs by itself after combining when post-processing is on; an admin can run it
// (again) from the card. Each finished stage opens the 100% view on its version.
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, unwrap } from '../../api/client'
import { Zoomable } from '../../components/CloseLook'
import { FilePath } from '../../components/FilePath'
import { Button } from '../../components/ui'
import { dateTimeText, durationText } from '../format'
import { useCanEdit } from '../settings/draft'
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
  const start = useMutation({
    mutationFn: async () => unwrap(await api.POST('/combined/{id}/post', { params: { path: { id } } })),
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
              ? `run ${run.run} · ${dateTimeText(run.finished_at)}`
              : 'not run yet'}
        </span>
        {admin && (
          <Button
            size="sm"
            variant="ghost"
            disabled={d.queued || start.isPending}
            onClick={() => start.mutate()}
            title="From the untouched file, with the current settings"
          >
            {run ? 'Run again' : 'Run post-processing'}
          </Button>
        )}
      </div>
      {run && (
        <ol className={c.postStages}>
          {run.stages.map((st, i) => (
            <li key={i} className={st.state === 'done' ? undefined : v.muted}>
              <span>
                <strong>{st.label}</strong>{' '}
                <span className={v.note}>
                  {st.state !== 'done'
                    ? st.reason
                    : st.step === 'trim'
                      ? 'registration border removed'
                      : `${st.tool_label || 'GraXpert'} · ${durationText(st.seconds ?? 0)}`}
                </span>
              </span>
              {st.state === 'done' && st.full && (
                <Zoomable target={{ kind: 'combined', id }} name={name} version={st.step} className={v.pill}>
                  View at 100%
                </Zoomable>
              )}
              {st.file_path && <FilePath path={st.file_path} download={st.download} />}
            </li>
          ))}
        </ol>
      )}
    </div>
  )
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
