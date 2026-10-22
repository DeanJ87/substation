// The collection page's ⋯ menu (006-DR-40): Archive files…, Bring back files…, Delete collection…. Archive and Bring
// back use the same move preview as the Files panel; Delete shows what it touches first, is refused while files
// move or combined masters remain, and offers Undo.
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from '@tanstack/react-router'
import { api, ApiError, unwrap } from '../../api/client'
import type { components } from '../../api/schema'
import { Modal } from '../../components/Modal'
import { PutAwayConfirm, type Impact } from '../../components/PutAway'
import { toast } from '../../components/Toasts'
import { Button } from '../../components/ui'
import { offerUndo } from '../changes/changes'
import { deletedText, VERBS } from '../changes/putAway'
import { bytesText, plural } from '../format'
import { Confirm, useCollectionFiles, type Direction } from './CollectionFiles'
import c from './collection.module.css'
import { Menu } from './ProjectCards'

type CollectionImpact = components['schemas']['CollectionImpactOut']

export function useCollectionImpact(id: number, enabled: boolean) {
  return useQuery({
    queryKey: ['collection-impact', id],
    enabled,
    staleTime: 0,
    queryFn: async () => unwrap(await api.GET('/collections/{id}/impact', { params: { path: { id } } })),
  })
}

const list = (xs: string[]) =>
  xs.length > 3 ? `${xs.slice(0, 3).join(', ')} and ${xs.length - 3} more` : xs.join(', ')

/** The three lines for deleting a collection, from its impact. */
export function collectionImpactLines(i: CollectionImpact): Impact {
  const where = i.libraries.filter((l) => l.files > 0)
  const files = where.length
    ? `${VERBS.delete.files.replace('.', '')}: ${where.map((l) => `${plural(l.files, 'file')} (${bytesText(l.bytes)}) ${l.files === 1 ? 'stays' : 'stay'} in ${l.name}`).join('; ')}.`
    : VERBS.delete.files
  const projects = i.projects.length
    ? `; ${plural(i.projects.length, 'project')} (${list(i.projects.map((p) => p.label))}) ${i.projects.length === 1 ? 'goes' : 'go'} with it`
    : ''
  const goals = i.projects.filter((p) => p.goals_set).length
  const links = [
    goals ? `Goals on ${plural(goals, 'project')} go with ${goals === 1 ? 'it' : 'them'}.` : '',
    i.finished.length ? `No longer linked to ${list(i.finished)}.` : '',
  ].filter(Boolean)
  return {
    files,
    records: `${plural(i.datasets, 'dataset')} ${i.datasets === 1 ? 'stays' : 'stay'}, as “Not in a collection”${projects}.`,
    links: links.join(' ') || 'No links or goals.',
  }
}

export type PutAwayStep = Direction | 'delete' | null

export function CollectionMenu({
  id,
  name,
  onMasters,
  open,
  setOpen,
}: {
  id: number
  name: string
  /** Opens the Masters tab: where combined masters that block a delete are. */
  onMasters: () => void
  /** Which dialog is open: the page holds it, so a toast elsewhere (every project done) can open Archive. */
  open: PutAwayStep
  setOpen: (step: PutAwayStep) => void
}) {
  const files = useCollectionFiles(id)
  const where = files.data?.location
  const items: (readonly [string, () => void])[] = [
    ...(where !== 'archive' ? ([[`${VERBS.archive.label}…`, () => setOpen('archive')]] as const) : []),
    ...(where === 'archive' || where === 'both'
      ? ([[`${VERBS.archive.restore}…`, () => setOpen('bring_back')]] as const)
      : []),
    ['Delete collection…', () => setOpen('delete')],
  ]
  return (
    <>
      <Menu label={`collection ${name}`} items={items} />
      {(open === 'archive' || open === 'bring_back') && (
        <Modal
          label={`${open === 'archive' ? VERBS.archive.label : VERBS.archive.restore}: ${name}`}
          onClose={() => setOpen(null)}
          size="sm"
        >
          <div className={c.dialog}>
            <h2 className={c.dialogTitle}>
              {open === 'archive' ? VERBS.archive.label : VERBS.archive.restore}
            </h2>
            <Confirm id={id} name={name} direction={open} onClose={() => setOpen(null)} />
          </div>
        </Modal>
      )}
      {open === 'delete' && (
        <DeleteCollection id={id} name={name} onMasters={onMasters} onClose={() => setOpen(null)} />
      )}
    </>
  )
}

function DeleteCollection({
  id,
  name,
  onMasters,
  onClose,
}: {
  id: number
  name: string
  onMasters: () => void
  onClose: () => void
}) {
  const qc = useQueryClient()
  const navigate = useNavigate()
  const impact = useCollectionImpact(id, true)
  const remove = useMutation({
    mutationFn: async () => unwrap(await api.DELETE('/collections/{id}', { params: { path: { id } } })),
    onSuccess: (r) => {
      offerUndo(qc, deletedText('collection', name), r.change_id)
      for (const w of r.warnings ?? []) toast(w)
      onClose()
      void navigate({ to: '/' })
    },
    onError: (e) => {
      // a refusal (a move started meanwhile) is shown in the dialog, not as a failure
      if (e instanceof ApiError && e.status === 409) void impact.refetch()
      toast(e instanceof Error ? e.message : "Couldn't delete the collection", true)
    },
    onSettled: () => {
      void qc.invalidateQueries({ queryKey: ['library'] })
      void qc.invalidateQueries({ queryKey: ['changes'] })
    },
  })
  const i = impact.data
  const blocked = i?.blockers ?? []
  return (
    <PutAwayConfirm
      verb="delete"
      name={`collection ${name}`}
      impact={i ? collectionImpactLines(i) : null}
      refused={blocked.length ? blocked.join(' ') : undefined}
      busy={remove.isPending}
      confirmLabel="Delete collection"
      onConfirm={() => remove.mutate()}
      onClose={onClose}
    >
      {i && i.combined.length > 0 && (
        <span>
          <Button
            size="sm"
            onClick={() => {
              onClose()
              onMasters()
            }}
          >
            Open its masters
          </Button>
        </span>
      )}
    </PutAwayConfirm>
  )
}
