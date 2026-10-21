// Finished (spec 020): the owner's hand-finished work, one folder per project in a library with the Completed role.
// Each project shows what it is, whether the renderer is offered it (or why not), the SubStation projects it's linked
// to, its files with their roles, its processing steps and when it last changed. Folders that don't fit the layout
// are listed with the reason, never guessed into a project.
import { Link } from '@tanstack/react-router'
import { Collapsible } from '../../components/Collapsible'
import { Button, EmptyState, ErrorState, PageLoading } from '../../components/ui'
import { agoText } from '../format'
import v from '../v2/v2.module.css'
import f from './finished.module.css'
import { KIND, roleText, useFinishedList, useRescanFinished, type Finished } from './queries'

/** The folder layout a Completed library is read with. */
export function FolderLayout() {
  return (
    <pre className={f.layout} aria-label="Folder layout">
      {`<Astro | Nightscapes | Videos>/<subject>/<name>/
    exports/   finished images
    web/       versions for the web
    social/    versions for social media
    project/   working files (listed, never sent to the renderer)`}
    </pre>
  )
}

const changed = (iso: string) =>
  new Date(iso).toLocaleString('en-GB', {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })

export function FinishedPage() {
  const q = useFinishedList()
  const rescan = useRescanFinished()
  if (q.isError)
    return (
      <ErrorState title="Couldn't load finished projects" onRetry={() => q.refetch()}>
        {q.error.message}
      </ErrorState>
    )
  const d = q.data
  if (!d) return <PageLoading />
  const projects = [...d.projects].sort(
    (a, b) =>
      a.kind.localeCompare(b.kind) || a.subject.localeCompare(b.subject) || a.name.localeCompare(b.name),
  )
  const offered = projects.filter((p) => p.offered).length
  return (
    <div className={v.page}>
      <header className={v.head}>
        <div>
          <h1>Finished</h1>
          <div className={v.sub}>
            Your hand-finished images, one folder per project. Link each to the SubStation project its subs
            came from and pick its final image, and the renderer can use it.
            {d.libraries.length > 0 &&
              ` From ${d.libraries.join(', ')}${projects.length ? `: ${offered} of ${projects.length} offered to the renderer` : ''}.`}
          </div>
        </div>
        {d.libraries.length > 0 && (
          <div className={v.actions}>
            <Button disabled={rescan.isPending} onClick={() => rescan.mutate()}>
              {rescan.isPending ? 'Rescanning…' : 'Rescan'}
            </Button>
          </div>
        )}
      </header>

      {d.libraries.length === 0 ? (
        <EmptyState title="No Completed library yet">
          <p>
            Finished projects come from a library with the Completed role. Give one that role in{' '}
            <Link to="/settings" hash="folders">
              Settings → Library
            </Link>
            , or mount a fourth library named <code>completed</code>. It can be read-only: SubStation only
            reads it.
          </p>
          <p>Inside it, each project is a folder laid out like this:</p>
          <FolderLayout />
        </EmptyState>
      ) : projects.length === 0 ? (
        <EmptyState title="No finished projects yet">
          <p>
            Nothing in {d.libraries.join(', ')} looks like a project folder yet. Each project is a folder laid
            out like this:
          </p>
          <FolderLayout />
        </EmptyState>
      ) : (
        <section className={v.card} aria-label="Finished projects">
          <div className={f.scroll}>
            <table className={v.table}>
              <thead>
                <tr>
                  <th>Project</th>
                  <th>Renderer</th>
                  <th>Linked to</th>
                  <th>Files</th>
                  <th>Processing</th>
                  <th>Changed</th>
                </tr>
              </thead>
              <tbody>
                {projects.map((p) => (
                  <Row key={p.id} p={p} />
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      {d.not_projects.length > 0 && (
        <Collapsible
          id="finished-not-projects"
          title="Not a project"
          meta={d.not_projects.length}
          defaultOpen={false}
        >
          <p className="muted">These folders don't fit the layout, so they aren't treated as projects.</p>
          <ul className={f.notList}>
            {d.not_projects.map(([path, reason]) => (
              <li key={path}>
                <span className={v.mono}>{path}</span> <span className="muted">· {reason}</span>
              </li>
            ))}
          </ul>
        </Collapsible>
      )}
    </div>
  )
}

function Row({ p }: { p: Finished }) {
  const roled = p.files.filter((x) => x.role)
  return (
    <tr>
      <td>
        <Link to="/finished/$id" params={{ id: String(p.id) }} className={f.name}>
          {p.name}
        </Link>
        <div className="muted">
          {KIND[p.kind] ?? p.kind} · {p.subject}
        </div>
        {p.missing && <div className={f.reason}>The folder is missing</div>}
      </td>
      <td className={f.status}>
        {p.offered ? (
          <span className={v.ok}>Offered</span>
        ) : (
          <span className={f.reason}>Not offered: {p.reason}</span>
        )}
      </td>
      <td>
        {p.links.length ? (
          <ul className={f.links}>
            {p.links.map((l) => (
              <li key={l.project_id}>
                <Link to="/collections/$id" params={{ id: String(l.collection_id) }}>
                  {l.collection_name}
                </Link>
                {l.project_name !== l.collection_name && <span className="muted"> · {l.project_name}</span>}
              </li>
            ))}
          </ul>
        ) : (
          <span className="muted">Not linked</span>
        )}
      </td>
      <td>
        <div>
          {p.files.length} file{p.files.length === 1 ? '' : 's'}
        </div>
        {roled.length > 0 && (
          <ul className={f.roles}>
            {roled.map((x) => (
              <li key={x.id}>
                <span className="muted">{roleText(x)}:</span> {x.rel_path.split('/').pop()}
              </li>
            ))}
          </ul>
        )}
      </td>
      <td className={f.status}>
        {p.processing.length ? p.processing.join(' → ') : <span className="muted">None yet</span>}
      </td>
      <td className={f.status} title={changed(p.changed_at)}>
        {agoText(p.changed_at)}
      </td>
    </tr>
  )
}
