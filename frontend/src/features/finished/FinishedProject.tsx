// One finished project (spec 020): link it to the SubStation projects whose subs made it (suggested by name, with
// the reasons, or picked by hand), say which file is the final image and which are starless, stars only, single
// filters or progressive stacks, list the processing steps, preview what the renderer receives, and write it as
// project.json into the folder when the library allows it. Changes are for admins; everyone else can look.
import { useQuery } from '@tanstack/react-query'
import { getRouteApi, Link } from '@tanstack/react-router'
import { useId, useState } from 'react'
import { api, ApiError, unwrap } from '../../api/client'
import { Collapsible } from '../../components/Collapsible'
import { toast } from '../../components/Toasts'
import { Button, ErrorState, PageLoading, Spinner } from '../../components/ui'
import { bytes } from '../format'
import { useSettings } from '../settings/draft'
import { useLibrary } from '../v2/hooks'
import v from '../v2/v2.module.css'
import f from './finished.module.css'
import {
  KIND,
  ROLE,
  SINGLE_ROLES,
  useFinished,
  useFinishedActions,
  useRenderData,
  useSuggestions,
  type Finished,
  type FinishedFile,
  type RoleChange,
} from './queries'
import { StepList } from './StepList'

const route = getRouteApi('/app/finished/$id')

const size = (n: number) => {
  const b = bytes(n)
  return `${b.value} ${b.unit}`
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
      <header className={v.head}>
        <div>
          <div className={v.crumbs}>
            <Link to="/finished">Finished</Link> / {KIND[p.kind] ?? p.kind} / {p.subject}
          </div>
          <h1>{p.name}</h1>
          <div className={v.sub}>
            <span className={v.mono}>
              {p.library}/{p.rel_path}
            </span>{' '}
            · changed{' '}
            {new Date(p.changed_at).toLocaleString('en-GB', {
              day: 'numeric',
              month: 'short',
              year: 'numeric',
              hour: '2-digit',
              minute: '2-digit',
            })}
          </div>
        </div>
      </header>

      {p.offered ? (
        <p className={v.ok}>Offered to the renderer.</p>
      ) : (
        <div className={v.banner} role="status">
          Not offered to the renderer yet: {p.reason}.
        </div>
      )}
      {!admin && settings.isSuccess && <p className="muted">Only an admin can change finished projects.</p>}

      <Links p={p} admin={admin} links={act.links} />
      <Files p={p} admin={admin} roles={act.roles} guess={act.guess} />

      <section className={`${v.card} ${v.cardPad} ${f.section}`} aria-labelledby="processing-h">
        <h2 id="processing-h">Processing steps</h2>
        <p className="muted">
          What you did to finish it, in order, as short labels (GraXpert, BlurXTerminator …). The renderer can
          show them.
        </p>
        <StepList
          steps={p.processing}
          disabled={!admin}
          saving={act.processing.isPending}
          onSave={(steps) =>
            act.processing.mutate(steps, { onSuccess: () => toast('Processing steps saved.') })
          }
        />
      </section>

      <section className={`${v.card} ${v.cardPad} ${f.section}`} aria-labelledby="json-h">
        <h2 id="json-h">project.json</h2>
        <p className="muted">
          Writes what the renderer receives into the project folder as <code>project.json</code>, so the
          folder describes itself. SubStation writes only that one file, and never over one it didn't write.
        </p>
        <ProjectJson p={p} admin={admin} write={act.projectJson} />
      </section>

      <Collapsible id="finished-render-data" title="Preview render data" defaultOpen={false}>
        <p className="muted">This is what the renderer receives for this project.</p>
        <RenderData id={p.id} />
      </Collapsible>
    </div>
  )
}

type Actions = ReturnType<typeof useFinishedActions>

function Links({ p, admin, links }: { p: Finished; admin: boolean; links: Actions['links'] }) {
  const sug = useSuggestions(p.id)
  const linked = new Set(p.links.map((l) => l.project_id))
  const ids = [...linked]
  const offers = (sug.data ?? []).filter((s) => !linked.has(s.project_id))
  return (
    <section className={`${v.card} ${v.cardPad} ${f.section}`} aria-labelledby="links-h">
      <h2 id="links-h">SubStation projects</h2>
      <p className="muted">
        The projects whose subs made this image. Their capture data (integration, nights, filters, quality)
        goes to the renderer. Link more than one when it was shot across several, e.g. two seasons.
      </p>
      {p.links.length ? (
        p.links.map((l) => (
          <div key={l.project_id} className={f.linked}>
            <span>
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
          </div>
        ))
      ) : (
        <p>Not linked yet.</p>
      )}
      {sug.isPending ? (
        <Spinner label="Finding suggestions" />
      ) : offers.length ? (
        <>
          <strong>Suggested</strong>
          {offers.map((s) => (
            <div key={s.project_id} className={f.suggestion}>
              <span>
                <strong>{s.collection_name}</strong>
                {s.project_name !== s.collection_name && <span className="muted"> · {s.project_name}</span>}
                <span className="muted"> · {s.reasons.join(', ')}</span>
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
            </div>
          ))}
        </>
      ) : (
        sug.isSuccess && <p className="muted">No suggestions: nothing shares its target or name.</p>
      )}
      {admin && (
        <PickProject linked={linked} busy={links.isPending} onPick={(id) => links.mutate([...ids, id])} />
      )}
    </section>
  )
}

/** Any SubStation project: choose its collection, then the project. */
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
      className={f.row}
      onSubmit={(e) => {
        e.preventDefault()
        if (project == null) return
        onPick(project)
        setProject(null)
      }}
    >
      <strong>Link another</strong>
      <label className={f.row}>
        Collection
        <select
          className={f.select}
          value={collection ?? ''}
          onChange={(e) => {
            setCollection(e.target.value ? Number(e.target.value) : null)
            setProject(null)
          }}
        >
          <option value="">Choose…</option>
          {collections.map((c) => (
            <option key={c.id} value={c.id}>
              {c.name}
            </option>
          ))}
        </select>
      </label>
      <label className={f.row}>
        Project
        <select
          className={f.select}
          value={project ?? ''}
          disabled={collection == null || !choices.length}
          onChange={(e) => setProject(e.target.value ? Number(e.target.value) : null)}
        >
          <option value="">
            {collection != null && projects.isSuccess && !choices.length ? 'None left to link' : 'Choose…'}
          </option>
          {choices.map((x) => (
            <option key={x.id} value={x.id}>
              {x.name}
            </option>
          ))}
        </select>
      </label>
      <Button type="submit" disabled={project == null || busy}>
        Link
      </Button>
    </form>
  )
}

type Draft = Record<number, Pick<RoleChange, 'role' | 'role_filter' | 'role_order'>>

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
  const current = (file: FinishedFile) =>
    draft[file.id] ?? { role: file.role, role_filter: file.role_filter, role_order: file.role_order }
  const changes: RoleChange[] = p.files
    .filter((file) => {
      const d = draft[file.id]
      if (!d) return false
      return (
        d.role !== file.role ||
        (d.role === 'per_filter' && d.role_filter !== file.role_filter) ||
        (d.role === 'progressive' && d.role_order !== file.role_order)
      )
    })
    .map((file) => ({ file_id: file.id, ...current(file) }))
  const problem = changes.find(
    (c) => (c.role === 'per_filter' && !c.role_filter?.trim()) || (c.role === 'progressive' && !c.role_order),
  )
  const set = (file: FinishedFile, next: Partial<Draft[number]>) => {
    const d = { ...draft, [file.id]: { ...current(file), ...next } }
    // final, starless and stars only belong to one file each: choosing one takes it from the others
    if (next.role && SINGLE_ROLES.has(next.role))
      for (const other of p.files)
        if (other.id !== file.id && current(other).role === next.role)
          d[other.id] = { role: '', role_filter: '', role_order: null }
    setDraft(d)
  }
  return (
    <section className={`${v.card} ${v.cardPad} ${f.section}`} aria-labelledby="files-h">
      <div className={f.sectionHead}>
        <h2 id="files-h">Files</h2>
        {admin && (
          <Button
            disabled={guess.isPending}
            onClick={() => guess.mutate(undefined, { onSuccess: () => setDraft({}) })}
          >
            Guess again from file names
          </Button>
        )}
      </div>
      <p className="muted">
        The renderer needs a final image; the others are optional. Names ending in -final, -starless, -stars
        or a filter name are picked up for you. Only PNG, JPEG and TIFF outside the project folder are offered
        to the renderer.
      </p>
      {p.files.length ? (
        <div className={f.scroll}>
          <table className={v.table}>
            <thead>
              <tr>
                <th>File</th>
                <th>Size</th>
                <th>Role</th>
              </tr>
            </thead>
            <tbody>
              {p.files.map((file) => (
                <FileRow key={file.id} file={file} cur={current(file)} admin={admin} onChange={set} />
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <p className="muted">No files in its exports, web, social or project folders yet.</p>
      )}
      {changes.length > 0 && (
        <div className={f.row}>
          <Button
            variant="primary"
            disabled={!!problem || roles.isPending}
            onClick={() =>
              roles.mutate(
                changes.map((c) => ({
                  ...c,
                  role_filter: c.role === 'per_filter' ? (c.role_filter ?? '').trim() : '',
                  role_order: c.role === 'progressive' ? c.role_order : null,
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
                : 'A progressive stack needs its position (1, 2, 3 …).'}
            </span>
          )}
        </div>
      )}
    </section>
  )
}

function FileRow({
  file,
  cur,
  admin,
  onChange,
}: {
  file: FinishedFile
  cur: Draft[number]
  admin: boolean
  onChange: (file: FinishedFile, next: Partial<Draft[number]>) => void
}) {
  const name = file.rel_path
  return (
    <tr className={file.servable ? undefined : f.unservable}>
      <td>
        <span className={f.path}>{name}</span>
        {file.missing && <div className={f.reason}>Missing</div>}
      </td>
      <td className={v.mono}>{size(file.size_bytes)}</td>
      <td>
        {file.servable ? (
          <div className={f.roleCell}>
            <select
              className={f.select}
              value={cur.role}
              disabled={!admin}
              aria-label={`Role of ${name}`}
              onChange={(e) =>
                onChange(file, {
                  role: e.target.value,
                  role_order: e.target.value === 'progressive' ? (cur.role_order ?? 1) : cur.role_order,
                })
              }
            >
              {Object.entries(ROLE).map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
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
            {cur.role === 'progressive' && (
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
          </div>
        ) : (
          <span>Not offered to the renderer</span>
        )}
      </td>
    </tr>
  )
}

function ProjectJson({ p, admin, write }: { p: Finished; admin: boolean; write: Actions['projectJson'] }) {
  const reasonId = useId()
  const why = !p.can_write_project_json
    ? p.project_json_reason || 'This library is mounted read-only.'
    : !p.links.length
      ? 'Link this project to a SubStation project first.'
      : ''
  return (
    <div className={f.row}>
      <Button
        disabled={!admin || !!why || write.isPending}
        aria-describedby={why ? reasonId : undefined}
        onClick={() => write.mutate(undefined, { onSuccess: () => toast('Wrote project.json.') })}
      >
        Write project.json
      </Button>
      {why && (
        <span id={reasonId} className={f.reason}>
          {why}
        </span>
      )}
      {write.error && (
        <p className={f.error} role="alert">
          {write.error.message}
        </p>
      )}
    </div>
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
