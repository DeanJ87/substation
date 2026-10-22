// Finished (spec 020): the owner's hand-finished work, one folder per project in a library with the Completed role.
// Each project shows its final image, what it is, the SubStation projects it's linked to, whether the renderer is
// offered it (or why not) and when it last changed. Folders that don't fit the layout
// are listed with the reason, never guessed into a project.
import { Link } from '@tanstack/react-router'
import { Collapsible } from '../../components/Collapsible'
import { useState } from 'react'
import { Button, EmptyState, ErrorState, PageLoading } from '../../components/ui'
import { agoText, dateTimeText, plural } from '../format'
import v from '../v2/v2.module.css'
import f from './finished.module.css'
import { StatusChip } from './FinishedProject'
import { imageUrl, KIND, useFinishedList, useRescanFinished, type Finished } from './queries'

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
          {d.libraries.length > 0 && projects.length > 0 && (
            <div className={v.sub}>
              {offered} of {plural(projects.length, 'project')} offered to the renderer
            </div>
          )}
        </div>
        {d.libraries.length > 0 && (
          <div className={v.actions}>
            <Button size="sm" disabled={rescan.isPending} onClick={() => rescan.mutate()}>
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
          <ul className={f.projects}>
            {projects.map((p) => (
              <Row key={p.id} p={p} />
            ))}
          </ul>
        </section>
      )}

      {d.not_projects.length > 0 && (
        <Collapsible
          id="finished-not-projects"
          title="Not a project"
          meta={d.not_projects.length}
          defaultOpen={false}
        >
          <ul className={f.notList} aria-label="Folders that don't fit the layout">
            {d.not_projects.map(([path, reason]) => (
              <li key={path}>
                <span className="mono">{path}</span> <span className="muted">· {reason}</span>
              </li>
            ))}
          </ul>
        </Collapsible>
      )}
    </div>
  )
}

function Row({ p }: { p: Finished }) {
  const final = p.files.find((x) => x.role === 'final' && !x.missing)
  // a final the server can't draw shows as "No preview", never as a broken image
  const [failed, setFailed] = useState(false)
  return (
    <li className={f.project}>
      <Link
        to="/finished/$id"
        params={{ id: String(p.id) }}
        className={f.projectThumb}
        tabIndex={-1}
        aria-hidden
      >
        {final && !failed ? (
          <img src={imageUrl(p.id, final.id)} alt="" loading="lazy" onError={() => setFailed(true)} />
        ) : final ? (
          'No preview'
        ) : (
          'No final'
        )}
      </Link>
      <div className={f.projectText}>
        <Link to="/finished/$id" params={{ id: String(p.id) }} className={f.name}>
          {p.name}
        </Link>
        <span className="muted">
          {KIND[p.kind] ?? p.kind} · {p.subject}
        </span>
        <span className={f.projectLinks}>
          {p.links.length ? (
            p.links.map((l, i) => (
              <span key={l.project_id}>
                {i > 0 && ', '}
                <Link to="/collections/$id" params={{ id: String(l.collection_id) }} className={f.quiet}>
                  {l.project_name}
                </Link>
              </span>
            ))
          ) : (
            <span className="muted">Not linked</span>
          )}
        </span>
        {p.missing && <span className={f.reason}>The folder is missing</span>}
      </div>
      <div className={f.projectSide}>
        <StatusChip p={p} />
        <span className="muted" title={dateTimeText(p.changed_at)}>
          {agoText(p.changed_at)}
        </span>
      </div>
    </li>
  )
}
