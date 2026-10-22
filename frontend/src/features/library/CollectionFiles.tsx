// Where a collection's files are, and Archive / Bring back (spec 013). Archive moves its files from the active library
// (fast storage, where new subs land) to that library's archive; Bring back is the same in the other direction. The
// page asks first, showing how many files and how much space will move, from which library to which; the move runs on
// the queue and shows its progress here and in Activity, and can be cancelled.
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { api, unwrap } from '../../api/client'
import type { components } from '../../api/schema'
import { Help } from '../../components/Help'
import { Button, Meter } from '../../components/ui'
import { offerUndo } from '../changes/changes'
import { bytesText, countText, plural } from '../format'
import v from '../v2/v2.module.css'
import c from './collection.module.css'

type Files = components['schemas']['CollectionFilesOut']
type Move = components['schemas']['CollectionMoveOut']
type Direction = 'archive' | 'bring_back'

const size = bytesText
const count = plural
const ROLE: Record<string, string> = { active: 'active', archive: 'archive' }
const VERB: Record<Direction, { label: string; doing: string; done: string }> = {
  archive: { label: 'Archive', doing: 'Archiving', done: 'Archived' },
  bring_back: { label: 'Bring back', doing: 'Bringing back', done: 'Brought back' },
}

export function useCollectionFiles(id: number) {
  return useQuery({
    queryKey: ['collection-files', id],
    queryFn: async () => unwrap(await api.GET('/collections/{id}/files', { params: { path: { id } } })),
    // a move under way is followed every few seconds
    refetchInterval: (q) => {
      const m = q.state.data?.move
      return m && (m.state === 'queued' || m.state === 'running') ? 3000 : false
    },
  })
}

/** "Archived · 16 files · 5.0 MB in big" — where its files are, in one line (D17). */
export function whereText(f: Pick<Files, 'location' | 'libraries'>): string {
  const of = (role: string) => f.libraries.filter((l) => l.role === role)
  const one = (role: string, lead: string) => {
    const ls = of(role)
    const files = ls.reduce((n, l) => n + l.files, 0)
    return `${lead} · ${count(files, 'file')} · ${ls.map((l) => `${size(l.bytes)} in ${l.name}`).join(', ')}`
  }
  const at = (role: string) =>
    of(role)
      .map((l) => `${size(l.bytes)} in ${l.name}`)
      .join(', ')
  switch (f.location) {
    case 'active':
      return one('active', 'Active')
    case 'archive':
      return one('archive', 'Archived')
    case 'both':
      return `Split · ${at('active')} (active), ${at('archive')} (archive)`
    default:
      return f.libraries.length
        ? f.libraries.map((l) => `${size(l.bytes)} in ${l.name}`).join(', ')
        : 'No files on disk'
  }
}

export function CollectionFiles({ id, name }: { id: number; name: string }) {
  const q = useCollectionFiles(id)
  const [asking, setAsking] = useState<Direction | null>(null)
  const f = q.data
  if (!f) return null
  const moving = f.move && (f.move.state === 'queued' || f.move.state === 'running') ? f.move : null
  const showArchive = f.location !== 'archive'
  const showBack = f.location === 'archive' || f.location === 'both'
  return (
    <section className={`${v.card} ${v.cardPad} ${c.files}`} aria-labelledby={`files-${id}`}>
      <h2 id={`files-${id}`} className={c.filesTitle}>
        Files
      </h2>
      <p>{whereText(f)}</p>
      {f.libraries.length > 1 && (
        <ul className={c.filesList}>
          {f.libraries.map((l) => (
            <li key={l.id}>
              <strong>{l.name}</strong>
              {ROLE[l.role] ? <span className={v.muted}> ({ROLE[l.role]})</span> : null} ·{' '}
              {count(l.files, 'file')} · {size(l.bytes)}
            </li>
          ))}
        </ul>
      )}
      {f.suggested && !moving && <Suggestion id={id} days={f.suggest_after_days} canDismiss={f.can_move} />}
      {f.move && <MoveStatus move={f.move} canCancel={f.can_move} />}
      {!moving && asking === null && (
        <div className={c.filesActions}>
          {showArchive && (
            <Choice
              direction="archive"
              choice={f.archive}
              canMove={f.can_move}
              onChoose={() => setAsking('archive')}
            />
          )}
          {showBack && (
            <Choice
              direction="bring_back"
              choice={f.bring_back}
              canMove={f.can_move}
              onChoose={() => setAsking('bring_back')}
            />
          )}
        </div>
      )}
      {asking && <Confirm id={id} name={name} direction={asking} onClose={() => setAsking(null)} />}
    </section>
  )
}

/** Archive or Bring back: a button, disabled with the reason beside it when it can't be done. */
function Choice({
  direction,
  choice,
  canMove,
  onChoose,
}: {
  direction: Direction
  choice: Files['archive']
  canMove: boolean
  onChoose: () => void
}) {
  const reason = !canMove ? "Read-only accounts can't move files." : choice.possible ? null : choice.reason
  const reasonId = `move-why-${direction}`
  return (
    <div className={c.choice}>
      <Button
        onClick={onChoose}
        disabled={!!reason}
        aria-describedby={reason ? reasonId : undefined}
        size="sm"
      >
        {VERB[direction].label}…
      </Button>
      {reason ? (
        <span id={reasonId} className={c.reason}>
          {reason}
        </span>
      ) : (
        <span className={v.muted}>
          {choice.from_library} → {choice.to_library}
        </span>
      )}
    </div>
  )
}

/** The confirm step: how many files and how much space, from which library to which. */
function Confirm({
  id,
  name,
  direction,
  onClose,
}: {
  id: number
  name: string
  direction: Direction
  onClose: () => void
}) {
  const qc = useQueryClient()
  const preview = useQuery({
    queryKey: ['move-preview', id, direction],
    queryFn: async () =>
      unwrap(
        await api.GET('/collections/{id}/move-preview', {
          params: { path: { id }, query: { direction } },
        }),
      ),
    staleTime: 0,
  })
  const start = useMutation({
    mutationFn: async () =>
      unwrap(await api.POST('/collections/{id}/move', { params: { path: { id } }, body: { direction } })),
    onSuccess: (m) => {
      offerUndo(
        qc,
        `${VERB[direction].doing} ${name}: ${count(m.files_total, 'file')} to ${m.to_library}. Follow it here or in Activity.`,
        m.change_id,
      )
      onClose()
    },
    onSettled: () => {
      void qc.invalidateQueries({ queryKey: ['collection-files', id] })
      void qc.invalidateQueries({ queryKey: ['library'] })
    },
    meta: { failed: "Couldn't start the move" },
  })
  const p = preview.data
  return (
    <div className={c.confirm} role="group" aria-label={`${VERB[direction].label} ${name}`}>
      {preview.isError && (
        <p className={c.reason} role="alert">
          {preview.error.message}
        </p>
      )}
      {!p && !preview.isError && <p className={v.muted}>Counting its files…</p>}
      {p && (
        <>
          <p>
            <strong>
              {VERB[direction].label} {name}:
            </strong>{' '}
            move {count(p.files, 'file')} ({size(p.bytes)}) from <strong>{p.from_library}</strong> to{' '}
            <strong>{p.to_library}</strong>.
          </p>
          <p className={v.muted}>
            {count(p.lights, 'sub')} and {count(p.calibration, 'calibration frame')}
            {p.calibration_kept
              ? `; ${count(p.calibration_kept, 'calibration frame')} that other collections in ${p.from_library} still use ${p.calibration_kept === 1 ? 'stays' : 'stay'} there`
              : ''}
            .{' '}
            <Help topic="How a move works">
              Each file keeps its folder and name, and is checked against its catalogue hash before the
              original is removed. Masters SubStation built stay where they are. The move runs on the queue;
              you can cancel it, and every file is left either moved or untouched.
            </Help>
          </p>
        </>
      )}
      <div className={c.filesActions}>
        <Button
          size="sm"
          variant="primary"
          disabled={!p || !p.files || start.isPending}
          onClick={() => start.mutate()}
        >
          {p ? `${VERB[direction].label} ${count(p.files, 'file')}` : VERB[direction].label}
        </Button>
        <Button size="sm" onClick={onClose}>
          Cancel
        </Button>
      </div>
    </div>
  )
}

function MoveStatus({ move, canCancel }: { move: Move; canCancel: boolean }) {
  const qc = useQueryClient()
  const cancel = useMutation({
    mutationFn: async () =>
      unwrap(await api.POST('/moves/{id}/cancel', { params: { path: { id: move.id } } })),
    onSettled: () => void qc.invalidateQueries({ queryKey: ['collection-files'] }),
    meta: { failed: "Couldn't cancel the move" },
  })
  const verb = VERB[(move.direction as Direction) ?? 'archive'] ?? VERB.archive
  const live = move.state === 'queued' || move.state === 'running'
  const pct = move.bytes_total ? Math.round((100 * move.bytes_done) / move.bytes_total) : 0
  const progress = `${countText(move.files_done)} of ${count(move.files_total, 'file')} · ${size(move.bytes_done)} of ${size(move.bytes_total)}`
  return (
    <div className={c.move} role="status">
      {live ? (
        <>
          <p>
            {move.state === 'queued' ? 'Waiting to start: ' : `${verb.doing}: `}
            {move.from_library} → {move.to_library} · {progress}
          </p>
          <Meter value={pct} max={100} label="Files moved" />
          {canCancel && (
            <Button size="sm" onClick={() => cancel.mutate()} disabled={cancel.isPending}>
              Cancel move
            </Button>
          )}
        </>
      ) : (
        <p className={v.muted}>
          {move.state === 'done'
            ? `${verb.done} to ${move.to_library}: ${progress}.`
            : move.state === 'cancelled'
              ? `Move to ${move.to_library} cancelled after ${progress}; the rest stayed where they were.`
              : `Move to ${move.to_library} stopped: ${move.error || 'it failed'}. Files not moved stayed where they were.`}
        </p>
      )}
      {move.problems > 0 && (
        <details>
          <summary>
            {count(move.problems, 'file')} left where {move.problems === 1 ? 'it was' : 'they were'}
          </summary>
          <ul className={c.filesList}>
            {move.problem_files.map((p) => (
              <li key={p.path}>
                <span className="mono">{p.path}</span>: {p.reason}
              </li>
            ))}
          </ul>
        </details>
      )}
    </div>
  )
}

function Suggestion({ id, days, canDismiss }: { id: number; days: number; canDismiss: boolean }) {
  const qc = useQueryClient()
  const dismiss = useMutation({
    mutationFn: async () =>
      unwrap(
        await api
          .POST('/collections/{id}/archive-suggestion/dismiss', { params: { path: { id } } })
          .then((r) => ({ ...r, data: null })),
      ),
    onSettled: () => {
      void qc.invalidateQueries({ queryKey: ['collection-files', id] })
      void qc.invalidateQueries({ queryKey: ['library'] })
    },
    meta: { failed: "Couldn't dismiss the suggestion" },
  })
  return (
    <p className={c.suggestion}>
      Worth archiving: no new subs for over {days} days, and it has a current master.{' '}
      {canDismiss && (
        <Button size="sm" variant="ghost" onClick={() => dismiss.mutate()} disabled={dismiss.isPending}>
          Not now
        </Button>
      )}
    </p>
  )
}
