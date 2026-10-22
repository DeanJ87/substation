// One finished project (spec 020): its files as pictures with their roles (final, starless, stars only, single
// filters, progressive stacks and processing steps), the SubStation projects whose subs made it, its distance, and a
// preview of what the renderer receives. Changes are for admins; everyone else can look.
import { useQuery } from '@tanstack/react-query'
import { getRouteApi, Link } from '@tanstack/react-router'
import { useEffect, useId, useState, type ReactNode } from 'react'
import { api, ApiError, unwrap } from '../../api/client'
import { Collapsible } from '../../components/Collapsible'
import { FilePath } from '../../components/FilePath'
import { Help } from '../../components/Help'
import { Modal } from '../../components/Modal'
import { toast } from '../../components/Toasts'
import { Button, ErrorState, Meter, PageLoading, Spinner } from '../../components/ui'
import { bytes, integrationText, pctText } from '../format'
import { useSettings } from '../settings/draft'
import { useLibrary } from '../v2/hooks'
import v from '../v2/v2.module.css'
import f from './finished.module.css'
import {
  BUILDING,
  imageUrl,
  KIND,
  ROLE,
  SINGLE_ROLES,
  useFinished,
  useFinishedActions,
  useGenerateProgression,
  useProgression,
  useRenderData,
  useSuggestions,
  type Checkpoint,
  type Finished,
  type FinishedFile,
  type RoleChange,
} from './queries'

const route = getRouteApi('/app/finished/$id')

const size = (n: number) => {
  const b = bytes(n)
  return `${b.value} ${b.unit}`
}
const baseName = (path: string) => path.split('/').pop() ?? path
const when = (iso: string) =>
  new Date(iso).toLocaleString('en-GB', {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })

/** "Offered to renderer", or "Not offered" with the reason behind a "?". */
export function StatusChip({ p }: { p: Pick<Finished, 'offered' | 'reason'> }) {
  return p.offered ? (
    <span className={`${f.chip} ${f.chipOk}`}>Offered to renderer</span>
  ) : (
    <span className={f.chipWrap}>
      <span className={`${f.chip} ${f.chipWarn}`} title={p.reason}>
        Not offered
      </span>
      <Help topic="Why not offered">{p.reason}</Help>
    </span>
  )
}

export function FinishedProject() {
  const id = Number(route.useParams().id)
  const q = useFinished(id)
  const settings = useSettings()
  const admin = !!settings.data?.can_edit
  const act = useFinishedActions(id)
  if (q.isError)
    return (
      <ErrorState title="Couldn't load this finished project" onRetry={() => q.refetch()}>
        {q.error.message}
      </ErrorState>
    )
  const p = q.data
  if (!p) return <PageLoading />
  return (
    <div className={v.page}>
      <header className={f.head}>
        <div className={v.crumbs}>
          <Link to="/finished">Finished</Link> / {KIND[p.kind] ?? p.kind} / {p.subject}
        </div>
        <div className={f.titleRow}>
          <h1>{p.name}</h1>
          <StatusChip p={p} />
        </div>
        <div className={f.meta}>
          <FilePath path={p.path} className={f.metaPath} />
          <span className="muted">Changed {when(p.changed_at)}</span>
          {!admin && settings.isSuccess && <span className="muted">· Read only</span>}
        </div>
      </header>

      <Files p={p} admin={admin} roles={act.roles} guess={act.guess} />
      <Steps p={p} />
      {/* nightscapes and videos have no subs to link and no target distance */}
      {p.kind === 'astro' && (
        <div className={f.pair}>
          <Links p={p} admin={admin} links={act.links} />
          <Distance p={p} admin={admin} set={act.distance} lookup={act.lookup} />
        </div>
      )}
      {/* the stacks after each night come from the linked projects' subs */}
      {p.kind === 'astro' && p.links.length > 0 && <Progression id={p.id} admin={admin} />}

      {/* nothing to preview until an astro project is linked (it asked anyway and logged a 409 on every load) */}
      {(p.links.length > 0 || p.kind !== 'astro') && (
        <Collapsible id="finished-render-data" title="Preview render data" defaultOpen={false}>
          <RenderData id={p.id} />
        </Collapsible>
      )}
    </div>
  )
}

type Actions = ReturnType<typeof useFinishedActions>

function SectionHead({
  id,
  title,
  help,
  children,
}: {
  id: string
  title: string
  help?: string
  children?: ReactNode
}) {
  return (
    <div className={f.sectionHead}>
      <h2 id={id}>
        {title}
        {help && <Help topic={title}>{help}</Help>}
      </h2>
      {children}
    </div>
  )
}

function Links({ p, admin, links }: { p: Finished; admin: boolean; links: Actions['links'] }) {
  const sug = useSuggestions(p.id)
  const linked = new Set(p.links.map((l) => l.project_id))
  const ids = [...linked]
  const offers = (sug.data ?? []).filter((s) => !linked.has(s.project_id))
  return (
    <section className={`${v.card} ${v.cardPad} ${f.section}`} aria-labelledby="links-h">
      <SectionHead
        id="links-h"
        title="Linked projects"
        help="The SubStation projects whose subs made this image. Their capture data goes to the renderer."
      />
      {p.links.length ? (
        <ul className={f.list}>
          {p.links.map((l) => (
            <li key={l.project_id} className={f.item}>
              <span className={f.itemName}>
                <Link to="/collections/$id" params={{ id: String(l.collection_id) }}>
                  {l.collection_name}
                </Link>
                {l.project_name !== l.collection_name && <span className="muted"> · {l.project_name}</span>}
              </span>
              {admin && (
                <Button
                  disabled={links.isPending}
                  aria-label={`Unlink ${l.project_name}`}
                  onClick={() => links.mutate(ids.filter((x) => x !== l.project_id))}
                >
                  Unlink
                </Button>
              )}
            </li>
          ))}
        </ul>
      ) : (
        <p className="muted">Not linked.</p>
      )}
      {sug.isPending ? (
        <Spinner label="Finding suggestions" />
      ) : (
        offers.length > 0 && (
          <div className={f.suggested}>
            <div className={f.label}>Suggested</div>
            <ul className={f.list}>
              {offers.slice(0, 5).map((s) => (
                <li key={s.project_id} className={f.item}>
                  <span className={f.itemName}>
                    {s.collection_name}
                    {s.project_name !== s.collection_name && (
                      <span className="muted"> · {s.project_name}</span>
                    )}
                    <span className={f.why}>{s.reasons.join(', ')}</span>
                  </span>
                  {admin && (
                    <Button
                      disabled={links.isPending}
                      aria-label={`Link ${s.project_name}`}
                      onClick={() => links.mutate([...ids, s.project_id])}
                    >
                      Link
                    </Button>
                  )}
                </li>
              ))}
            </ul>
          </div>
        )
      )}
      {admin && (
        <PickProject linked={linked} busy={links.isPending} onPick={(id) => links.mutate([...ids, id])} />
      )}
    </section>
  )
}

/** Any SubStation project: choose its collection, then one of that collection's projects. */
function PickProject({
  linked,
  busy,
  onPick,
}: {
  linked: Set<number>
  busy: boolean
  onPick: (id: number) => void
}) {
  const lib = useLibrary()
  const [collection, setCollection] = useState<number | null>(null)
  const [project, setProject] = useState<number | null>(null)
  const projects = useQuery({
    queryKey: ['collection-projects', collection],
    enabled: collection != null,
    queryFn: async () =>
      unwrap(await api.GET('/collections/{id}/projects', { params: { path: { id: collection! } } })),
  })
  const collections = [...(lib.data?.collections ?? [])].sort((a, b) => a.name.localeCompare(b.name))
  const choices = (projects.data?.projects ?? []).filter((x) => !linked.has(x.id))
  return (
    <form
      className={f.pick}
      aria-label="Link another project"
      onSubmit={(e) => {
        e.preventDefault()
        if (project == null) return
        onPick(project)
        setProject(null)
      }}
    >
      <select
        className={f.select}
        aria-label="Collection"
        value={collection ?? ''}
        onChange={(e) => {
          setCollection(e.target.value ? Number(e.target.value) : null)
          setProject(null)
        }}
      >
        <option value="">Collection…</option>
        {collections.map((c) => (
          <option key={c.id} value={c.id}>
            {c.name}
          </option>
        ))}
      </select>
      <select
        className={f.select}
        aria-label="Project"
        value={project ?? ''}
        disabled={collection == null || !choices.length}
        onChange={(e) => setProject(e.target.value ? Number(e.target.value) : null)}
      >
        <option value="">
          {collection != null && projects.isSuccess && !choices.length ? 'None left' : 'Project…'}
        </option>
        {choices.map((x) => (
          <option key={x.id} value={x.id}>
            {x.name}
          </option>
        ))}
      </select>
      <Button type="submit" disabled={project == null || busy}>
        Link
      </Button>
    </form>
  )
}

type Cur = Pick<RoleChange, 'role' | 'role_filter' | 'role_order' | 'role_label'>
type Draft = Record<number, Cur>
const ORDERED = new Set(['progressive', 'step'])

function Files({
  p,
  admin,
  roles,
  guess,
}: {
  p: Finished
  admin: boolean
  roles: Actions['roles']
  guess: Actions['guess']
}) {
  const [draft, setDraft] = useState<Draft>({})
  const [shown, setShown] = useState<FinishedFile | null>(null)
  const current = (file: FinishedFile): Cur =>
    draft[file.id] ?? {
      role: file.role,
      role_filter: file.role_filter,
      role_order: file.role_order,
      role_label: file.role_label,
    }
  const changes: RoleChange[] = p.files
    .filter((file) => {
      const d = draft[file.id]
      if (!d) return false
      return (
        d.role !== file.role ||
        (d.role === 'per_filter' && d.role_filter !== file.role_filter) ||
        (ORDERED.has(d.role) && d.role_order !== file.role_order) ||
        (d.role === 'step' && d.role_label !== file.role_label)
      )
    })
    .map((file) => ({ file_id: file.id, ...current(file) }))
  const problem = changes.find(
    (c) =>
      (c.role === 'per_filter' && !c.role_filter?.trim()) ||
      (ORDERED.has(c.role) && !c.role_order) ||
      (c.role === 'step' && !c.role_label?.trim()),
  )
  const set = (file: FinishedFile, next: Partial<Cur>) => {
    const d = { ...draft, [file.id]: { ...current(file), ...next } }
    // final, starless and stars only belong to one file each: choosing one takes it from the others
    if (next.role && SINGLE_ROLES.has(next.role))
      for (const other of p.files)
        if (other.id !== file.id && current(other).role === next.role)
          d[other.id] = { role: '', role_filter: '', role_order: null, role_label: '' }
    setDraft(d)
  }
  const nextOrder = (role: string) =>
    Math.max(
      0,
      ...p.files
        .map((x) => current(x))
        .filter((c) => c.role === role)
        .map((c) => c.role_order ?? 0),
    ) + 1
  const cards = p.files.filter((x) => x.servable)
  const working = p.files.filter((x) => !x.servable)
  return (
    <section className={`${v.card} ${v.cardPad} ${f.section}`} aria-labelledby="files-h">
      <SectionHead
        id="files-h"
        title="Files"
        help="The renderer needs a final image; every other role is optional. Files named …final, …starless, …stars or after a filter are picked up for you. Only PNG, JPEG and TIFF outside project/ are offered."
      >
        {admin && (
          <Button
            disabled={guess.isPending}
            onClick={() => guess.mutate(undefined, { onSuccess: () => setDraft({}) })}
          >
            Guess again
          </Button>
        )}
      </SectionHead>
      {cards.length ? (
        <ul className={f.grid}>
          {cards.map((file) => (
            <FileCard
              key={file.id}
              p={p}
              file={file}
              cur={current(file)}
              admin={admin}
              onChange={set}
              onOpen={() => setShown(file)}
              nextOrder={nextOrder}
            />
          ))}
        </ul>
      ) : (
        <p className="muted">No images in exports, web or social yet.</p>
      )}
      {working.length > 0 && (
        <details className={f.working}>
          <summary>
            Working files <span className={f.count}>{working.length}</span>
          </summary>
          <ul className={f.workingList}>
            {working.map((file) => (
              <li key={file.id}>
                <span className={f.path}>{file.rel_path}</span>
                <span className={v.mono}>{size(file.size_bytes)}</span>
              </li>
            ))}
          </ul>
        </details>
      )}
      {changes.length > 0 && (
        <div className={f.saveBar}>
          <Button
            variant="primary"
            disabled={!!problem || roles.isPending}
            onClick={() =>
              roles.mutate(
                changes.map((c) => ({
                  ...c,
                  role_filter: c.role === 'per_filter' ? (c.role_filter ?? '').trim() : '',
                  role_order: ORDERED.has(c.role) ? c.role_order : null,
                  role_label: c.role === 'step' ? (c.role_label ?? '').trim() : '',
                })),
                {
                  onSuccess: () => {
                    setDraft({})
                    toast('File roles saved.')
                  },
                },
              )
            }
          >
            Save roles
          </Button>
          <Button onClick={() => setDraft({})}>Discard</Button>
          {problem && (
            <span className={f.reason} role="status">
              {problem.role === 'per_filter'
                ? 'A single-filter image needs its filter.'
                : problem.role === 'step' && problem.role_order
                  ? 'A processing step needs a label.'
                  : 'Give it a position (1, 2, 3 …).'}
            </span>
          )}
        </div>
      )}
      {shown && (
        <Modal label={baseName(shown.rel_path)} onClose={() => setShown(null)}>
          <h2 className={f.previewName}>{baseName(shown.rel_path)}</h2>
          <img className={f.preview} src={imageUrl(p.id, shown.id, 'preview')} alt={shown.rel_path} />
        </Modal>
      )}
    </section>
  )
}

function Thumb({ p, file, onOpen }: { p: Finished; file: FinishedFile; onOpen: () => void }) {
  const [failed, setFailed] = useState(false)
  if (file.missing || failed)
    return (
      <div className={f.thumb} aria-hidden="true">
        <span className={f.thumbNone}>{file.missing ? 'Missing' : 'No preview'}</span>
      </div>
    )
  return (
    <button type="button" className={f.thumb} aria-label={`Preview ${file.rel_path}`} onClick={onOpen}>
      <img src={imageUrl(p.id, file.id)} alt="" loading="lazy" onError={() => setFailed(true)} />
    </button>
  )
}

function FileCard({
  p,
  file,
  cur,
  admin,
  onChange,
  onOpen,
  nextOrder,
}: {
  p: Finished
  file: FinishedFile
  cur: Cur
  admin: boolean
  onChange: (file: FinishedFile, next: Partial<Cur>) => void
  onOpen: () => void
  nextOrder: (role: string) => number
}) {
  const name = file.rel_path
  return (
    <li className={f.fileCard}>
      <Thumb p={p} file={file} onOpen={onOpen} />
      <div className={f.fileBody}>
        <div className={f.fileName} title={name}>
          {baseName(name)}
        </div>
        <div className={f.fileMeta}>
          {file.section} · <span className={v.mono}>{size(file.size_bytes)}</span>
        </div>
        <select
          className={f.select}
          value={cur.role}
          disabled={!admin}
          aria-label={`Role of ${name}`}
          onChange={(e) => {
            const role = e.target.value
            onChange(file, {
              role,
              role_order: ORDERED.has(role) && role !== cur.role ? nextOrder(role) : cur.role_order,
            })
          }}
        >
          {Object.entries(ROLE).map(([value, label]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </select>
        {(cur.role === 'per_filter' || ORDERED.has(cur.role)) && (
          <div className={f.roleExtra}>
            {ORDERED.has(cur.role) && (
              <input
                className={`${f.input} ${f.small}`}
                type="number"
                min={1}
                step={1}
                value={cur.role_order ?? ''}
                disabled={!admin}
                aria-label={`Order of ${name}`}
                onChange={(e) =>
                  onChange(file, { role_order: e.target.value === '' ? null : Number(e.target.value) })
                }
              />
            )}
            {cur.role === 'step' && (
              <input
                className={f.input}
                value={cur.role_label ?? ''}
                disabled={!admin}
                maxLength={100}
                placeholder="e.g. GraXpert"
                aria-label={`Step label of ${name}`}
                onChange={(e) => onChange(file, { role_label: e.target.value })}
              />
            )}
            {cur.role === 'per_filter' && (
              <input
                className={f.input}
                value={cur.role_filter ?? ''}
                disabled={!admin}
                maxLength={100}
                placeholder="e.g. Hα"
                aria-label={`Filter of ${name}`}
                onChange={(e) => onChange(file, { role_filter: e.target.value })}
              />
            )}
          </div>
        )}
      </div>
    </li>
  )
}

/** The files given the Processing step role, in order: what the image looked like after each step. */
function Steps({ p }: { p: Finished }) {
  const steps = p.files
    .filter((x) => x.role === 'step')
    .sort((a, b) => (a.role_order ?? 0) - (b.role_order ?? 0))
  return (
    <section className={`${v.card} ${v.cardPad} ${f.section}`} aria-labelledby="steps-h">
      <SectionHead
        id="steps-h"
        title="Processing steps"
        help="Give a file the Processing step role, with its position and what you did, to show the image after each step."
      />
      {steps.length ? (
        <ol className={f.steps}>
          {steps.map((s) => (
            <li key={s.id} className={f.step}>
              <span className={f.stepThumb}>
                {!s.missing && <img src={imageUrl(p.id, s.id)} alt="" loading="lazy" />}
              </span>
              <span className={f.stepText}>
                <span className={v.mono}>{s.role_order ?? '?'}</span> · {s.role_label || baseName(s.rel_path)}
              </span>
            </li>
          ))}
        </ol>
      ) : (
        <p className="muted">None yet.</p>
      )}
    </section>
  )
}

const STATE: Record<string, string> = {
  queued: 'Queued',
  running: 'Building',
  done: 'Built',
  failed: 'Failed',
  cancelled: 'Cancelled',
}

/** The cumulative stacks after each night (020-DR-15): a state line, Generate or Rebuild, and the stacks in order. */
function Progression({ id, admin }: { id: number; admin: boolean }) {
  const q = useProgression(id)
  const generate = useGenerateProgression(id)
  const [shown, setShown] = useState<number | null>(null)
  const prog = q.data
  const building = !!prog && BUILDING.has(prog.state)
  // "none" with a reason is the server saying it can't be built (a mosaic, too few subs …)
  const blocked = !!prog && (prog.state === 'unavailable' || (prog.state === 'none' && !!prog.reason))
  const done = prog?.state === 'done'
  const refused = generate.data?.error
  const checkpoints = [...(prog?.checkpoints ?? [])].sort((a, b) => a.order - b.order)
  return (
    <section className={`${v.card} ${v.cardPad} ${f.section}`} aria-labelledby="progression-h">
      <SectionHead
        id="progression-h"
        title="Progression"
        help="A stack after each night, all with the full stack's stretch, so you see noise fall. Single-field projects only for now."
      >
        {admin && prog && !blocked && !building && (
          <Button disabled={generate.isPending} onClick={() => generate.mutate(done)}>
            {done ? 'Rebuild' : 'Generate'}
          </Button>
        )}
      </SectionHead>
      {!prog ? (
        q.isError ? (
          <p className={f.error}>{q.error.message}</p>
        ) : (
          <Spinner label="Loading the progression" />
        )
      ) : (
        <>
          {building && (
            <div className={f.progState} role="status">
              <span>
                {STATE[prog.state]}
                {prog.step && <span className="muted"> · {prog.step}</span>}
              </span>
              <span className={v.mono}>{pctText(prog.progress)}</span>
              <Meter value={prog.progress} label="Progression progress" />
            </div>
          )}
          {blocked ? (
            <p className={f.progReason}>{prog.reason || 'Not available for this project.'}</p>
          ) : (
            (prog.state === 'failed' || prog.state === 'cancelled') && (
              <p className={prog.state === 'failed' ? f.error : 'muted'}>
                {STATE[prog.state]}
                {prog.reason && `: ${prog.reason}`}
              </p>
            )
          )}
          {prog.state === 'none' && !blocked && (
            <p className="muted">Not built yet: a stack after each night of the linked subs.</p>
          )}
          {refused && (
            <p className={f.error} role="alert">
              {refused}
            </p>
          )}
          {checkpoints.length > 0 && (
            <ol className={f.steps} aria-label="Stacks after each night">
              {checkpoints.map((c, i) => (
                <li key={c.order} className={f.checkpoint}>
                  <button
                    type="button"
                    className={f.stepThumb}
                    aria-label={`Open ${c.label}`}
                    onClick={() => setShown(i)}
                  >
                    <img src={c.image_url} alt="" loading="lazy" />
                  </button>
                  <span className={f.stepText} title={checkpointText(c)}>
                    {checkpointText(c)}
                  </span>
                </li>
              ))}
            </ol>
          )}
        </>
      )}
      {shown != null && checkpoints[shown] && (
        <CheckpointViewer
          checkpoints={checkpoints}
          at={shown}
          onMove={setShown}
          onClose={() => setShown(null)}
        />
      )}
    </section>
  )
}

/** "3–9 Oct · 4h 30m · 54 subs" */
const checkpointText = (c: Checkpoint) =>
  `${c.label} · ${integrationText(c.integration_s)} · ${c.subs} ${c.subs === 1 ? 'sub' : 'subs'}`

function CheckpointViewer({
  checkpoints,
  at,
  onMove,
  onClose,
}: {
  checkpoints: Checkpoint[]
  at: number
  onMove: (i: number) => void
  onClose: () => void
}) {
  const c = checkpoints[at]
  const last = checkpoints.length - 1
  useEffect(() => {
    const key = (e: KeyboardEvent) => {
      if (e.key === 'ArrowLeft' && at > 0) onMove(at - 1)
      if (e.key === 'ArrowRight' && at < last) onMove(at + 1)
    }
    window.addEventListener('keydown', key)
    return () => window.removeEventListener('keydown', key)
  }, [at, last, onMove])
  return (
    <Modal label={`Progression: ${c.label}`} onClose={onClose}>
      <h2 className={f.previewName}>
        {checkpointText(c)}
        <span className={f.progCount}>
          {at + 1} of {checkpoints.length}
        </span>
      </h2>
      <img className={f.preview} src={c.image_url} alt={`Stack after ${c.label}`} />
      <div className={f.progNav}>
        <Button disabled={at === 0} onClick={() => onMove(at - 1)}>
          ← Prev
        </Button>
        <Button disabled={at === last} onClick={() => onMove(at + 1)}>
          Next →
        </Button>
      </div>
    </Modal>
  )
}

function Distance({
  p,
  admin,
  set,
  lookup,
}: {
  p: Finished
  admin: boolean
  set: Actions['distance']
  lookup: Actions['lookup']
}) {
  const hintId = useId()
  const manual = p.distance_source === 'manual'
  const error = lookup.data?.error
  return (
    <section className={`${v.card} ${v.cardPad} ${f.section}`} aria-labelledby="distance-h">
      <SectionHead
        id="distance-h"
        title="Distance"
        help="Looked up from SIMBAD by the subject's name, or typed in. A distance you type is kept: clear it to look it up again."
      />
      <div className={f.distance}>
        <DistanceInput
          key={p.distance_ly ?? 'none'}
          value={p.distance_ly}
          disabled={!admin || set.isPending}
          onSave={(n) => set.mutate(n)}
        />
        <span className="muted">ly</span>
        {admin && (
          <>
            <Button
              disabled={manual || lookup.isPending}
              aria-describedby={manual ? hintId : undefined}
              onClick={() => lookup.mutate()}
            >
              {lookup.isPending ? 'Looking up…' : 'Look up'}
            </Button>
            {p.distance_ly != null && (
              <Button disabled={set.isPending} onClick={() => set.mutate(null)}>
                Clear
              </Button>
            )}
          </>
        )}
      </div>
      {p.distance_source && <div className={f.source}>{manual ? 'Set by hand' : p.distance_source}</div>}
      {admin && manual && (
        <div id={hintId} className={f.hint}>
          Clear it to look it up.
        </div>
      )}
      {error && (
        <p className={f.error} role="alert">
          {error}
        </p>
      )}
    </section>
  )
}

function DistanceInput({
  value,
  disabled,
  onSave,
}: {
  value: number | null
  disabled: boolean
  onSave: (n: number | null) => void
}) {
  const [text, setText] = useState(value == null ? '' : String(value))
  const commit = () => {
    const t = text.replace(/[,\s]/g, '')
    if (t === '') {
      if (value != null) onSave(null)
      return
    }
    const n = Number(t)
    if (!Number.isFinite(n) || n <= 0) {
      setText(value == null ? '' : String(value))
      return
    }
    if (n !== value) onSave(n)
  }
  return (
    <input
      className={`${f.input} ${f.distanceInput}`}
      inputMode="decimal"
      value={text}
      disabled={disabled}
      placeholder="—"
      aria-label="Distance in light years"
      onChange={(e) => setText(e.target.value)}
      onBlur={commit}
      onKeyDown={(e) => {
        if (e.key === 'Enter') {
          e.preventDefault()
          e.currentTarget.blur() // blurring saves it
        }
      }}
    />
  )
}

function RenderData({ id }: { id: number }) {
  const q = useRenderData(id)
  if (q.isPending) return <Spinner label="Building the render data" />
  if (q.isError)
    return (
      <p className={q.error instanceof ApiError && q.error.status === 409 ? 'muted' : f.error}>
        {q.error.message}
      </p>
    )
  const text = JSON.stringify(q.data, null, 2)
  return (
    // a read-only text box: it scrolls, takes focus from the keyboard and selects for copying
    <textarea
      className={f.json}
      readOnly
      aria-label="Render data"
      rows={Math.min(30, text.split('\n').length + 1)}
      value={text}
    />
  )
}
