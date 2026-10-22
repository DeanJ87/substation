// Reconciliation list (T079): what SubStation couldn't settle on its own, grouped by kind, field and folder so
// one answer fixes a whole night. Answers are stored by content, so they survive moves and re-imports. Each group
// shows what its files are by one example (001-DR-xx): type, place, header values, a thumbnail, and what's needed.
import { Glance, glanceUrl } from '../../components/Glance'
import { Zoomable } from '../../components/CloseLook'
import { toast } from '../../components/Toasts'
import { useMemo, useState } from 'react'
import { Button, EmptyState, ErrorState } from '../../components/ui'
import { Collapsible } from '../../components/Collapsible'
import { LoadMore } from '../../components/LoadMore'
import { useProgressive } from '../../components/useProgressive'
import { useLiveEvents } from '../../api/events'
import { countText, fileName, shortDateText, signed } from '../format'
import {
  FIELD_LABEL,
  FRAME_TYPES,
  useAddIgnore,
  useDismiss,
  useReconciliation,
  useResolve,
  type ReconItem,
} from '../metadata/queries'
import { useQueryClient } from '@tanstack/react-query'
import { globMatch, groupPlace, likeGlob, needLine, tempText, typeLabel, type Example } from './describe'
import s from './reconciliation.module.css'

const KIND: Record<string, (field: string | null) => string> = {
  missing_field: (f) => `${FIELD_LABEL[f ?? ''] ?? f} missing`,
  classification_unknown: () => 'Frame type unknown',
  frame_missing: () => 'Missing from disk',
  bad_without_twin: () => 'Rejected in NINA, no original',
  master_metadata: (f) => `No ${(FIELD_LABEL[f ?? ''] ?? f ?? '').toLowerCase()}`,
  ambiguous_master: () => 'More than one master fits',
}
/** Each kind's section heading, above its groups. */
const KIND_TITLE: Record<string, string> = {
  missing_field: 'Missing values',
  classification_unknown: 'Frame type unknown',
  frame_missing: 'Missing from disk',
  master_metadata: 'Masters missing values',
  ambiguous_master: 'More than one master fits',
  bad_without_twin: 'Rejected in NINA, no original',
}
const ORDER = [
  'missing_field',
  'classification_unknown',
  'frame_missing',
  'master_metadata',
  'ambiguous_master',
  'bad_without_twin',
]

interface Group {
  key: string
  kind: string
  field: string | null
  folder: string
  example: Example | null
  items: ReconItem[]
}

function folderOf(path: string) {
  const i = path.lastIndexOf('/')
  return i < 0 ? '' : path.slice(0, i + 1)
}

/** Groups as the server keys them (kind, field, library, folder); the example rides on the first item. */
function group(items: ReconItem[]): Group[] {
  const map = new Map<string, Group>()
  for (const it of items) {
    const folder = it.frame ? folderOf(it.frame.primary_path) : ''
    const key = it.group || `${it.kind}|${it.field ?? ''}|${folder}`
    const g = map.get(key) ?? { key, kind: it.kind, field: it.field, folder, example: null, items: [] }
    g.example ??= it.example ?? null
    g.items.push(it)
    map.set(key, g)
  }
  return [...map.values()].sort(
    (a, b) => ORDER.indexOf(a.kind) - ORDER.indexOf(b.kind) || a.folder.localeCompare(b.folder),
  )
}

export function ReconciliationList() {
  const qc = useQueryClient()
  const [status, setStatus] = useState<'open' | 'resolved' | 'dismissed'>('open')
  const q = useReconciliation(status)
  // while answers are in flight a refetch would bring answered items back; they refresh once it settles
  const refresh = () => {
    if (!qc.isMutating({ mutationKey: ['reconcile'] }) && !qc.isMutating({ mutationKey: ['ignore'] }))
      void qc.invalidateQueries({ queryKey: ['reconciliation'] })
  }
  useLiveEvents({ 'frame.updated': refresh, 'frame.catalogued': refresh })
  const groups = useMemo(() => group(q.data ?? []), [q.data])
  // one folding section per kind, in the order groups already come in
  const byKind = useMemo(() => {
    const m = new Map<string, Group[]>()
    for (const g of groups) m.set(g.kind, [...(m.get(g.kind) ?? []), g])
    return [...m.entries()]
  }, [groups])

  return (
    <div className={s.page}>
      <header className={s.header}>
        <div>
          <h1>Reconcile</h1>
          <p className="muted">Values missing from headers and path patterns.</p>
        </div>
        <select
          aria-label="Show"
          value={status}
          onChange={(e) => setStatus(e.target.value as typeof status)}
          className={s.select}
        >
          <option value="open">Open</option>
          <option value="resolved">Resolved</option>
          <option value="dismissed">Dismissed</option>
        </select>
      </header>
      {q.isError && (
        <ErrorState title="Couldn't load the list" onRetry={() => q.refetch()}>
          {q.error.message}
        </ErrorState>
      )}
      {q.isSuccess && groups.length === 0 && (
        <EmptyState title={status === 'open' ? 'Nothing to reconcile' : `Nothing ${status}`}>
          {status === 'open' ? 'All files have the values they need.' : 'None yet.'}
        </EmptyState>
      )}
      {byKind.map(([kind, gs]) => (
        <KindSection key={kind} kind={kind} groups={gs} status={status} all={q.data ?? []} />
      ))}
    </div>
  )
}

/** All the groups of one kind, a slice at a time inside their own scroll. */
function KindSection({
  kind,
  groups,
  status,
  all,
}: {
  kind: string
  groups: Group[]
  status: string
  all: ReconItem[]
}) {
  const { visible, hasMore, more } = useProgressive(groups, 20, status)
  const files = groups.reduce((n, g) => n + g.items.length, 0)
  return (
    <Collapsible
      id={`reconcile-${kind}`}
      title={KIND_TITLE[kind] ?? kind}
      meta={`${countText(files)} file${files === 1 ? '' : 's'} · ${groups.length} group${groups.length === 1 ? '' : 's'}`}
    >
      <div className={s.pane}>
        <ul className={s.groups}>
          {visible.map((g) => (
            <GroupCard key={g.key} g={g} open={status === 'open'} all={all} />
          ))}
        </ul>
        <LoadMore hasMore={hasMore} loading={false} onMore={more} />
      </div>
    </Collapsible>
  )
}

function GroupCard({ g, open, all }: { g: Group; open: boolean; all: ReconItem[] }) {
  const resolve = useResolve()
  const dismiss = useDismiss()
  const ignore = useAddIgnore()
  const [value, setValue] = useState('')
  const [expanded, setExpanded] = useState(false)
  const first = g.items[0]
  const ex = g.example
  const suggestion = first.suggestion as { value?: string; why?: string } | null
  const needsValue = ['missing_field', 'classification_unknown', 'master_metadata'].includes(g.kind)
  const n = g.items.length
  const ids = g.items.map((it) => it.id)
  // every answer takes the whole group off the list at once; a failure puts it back with a note
  const setAll = (v: { value?: string; accept_suggestion?: boolean }) =>
    resolve.mutate({ ids: [first.id], hide: ids, ...v, apply_to_similar: true })
  const acknowledge = () => resolve.mutate({ ids })
  const dismissAll = () => dismiss.mutate(ids)

  const where = ex ? `${ex.library ?? ''}/${ex.folder ? `${ex.folder}/` : ''}` : g.folder
  const glob = ex ? likeGlob(ex.file_name) : null
  // an ignore rule takes every open item it covers off the list, not just this group's
  const ignoreFolder = () => {
    if (!ex?.folder || ex.library_id == null) return
    const lib = String(ex.library_id)
    const f = ex.folder
    const hide = all
      .filter((it) => {
        const p = groupPlace(it.group)
        return p.library === lib && (p.folder === f || p.folder.startsWith(`${f}/`))
      })
      .map((it) => it.id)
    ignore.mutate({ rules: [{ kind: 'folder', value: f, library_id: ex.library_id }], recon: hide })
    toast(`Ignoring ${where}. Undo in Settings → Ignored.`)
  }
  const ignoreLike = () => {
    if (!glob || ex?.library_id == null) return
    const lib = String(ex.library_id)
    const hide = all
      .filter(
        (it) =>
          it.frame &&
          groupPlace(it.group).library === lib &&
          globMatch(glob, fileName(it.frame.primary_path)),
      )
      .map((it) => it.id)
    ignore.mutate({ rules: [{ kind: 'glob', value: glob, library_id: ex.library_id }], recon: hide })
    toast(`Ignoring files like ${glob} in ${ex.library}. Undo in Settings → Ignored.`)
  }

  return (
    <li className={s.group}>
      <div className={s.body}>
        {ex && <Thumb sha={ex.sha256} name={ex.file_name} />}
        <div className={s.main}>
          <div className={s.groupHead}>
            <div>
              <h2 className={s.title}>
                <span className={s.type}>{typeLabel(ex?.frame_type ?? first.frame?.frame_type)}</span>
                {(KIND[g.kind] ?? ((k) => k))(g.field)}
                <span className={s.count}>
                  {countText(n)} file{n === 1 ? '' : 's'}
                </span>
              </h2>
              {where && (
                <div className={s.where}>
                  <span className="muted">in</span> <span className="mono">{where}</span>
                  {ex && (
                    <>
                      {' '}
                      <span className="muted">· e.g.</span>{' '}
                      <span className="mono">
                        <Glance sha={ex.sha256} label={ex.file_name}>
                          {ex.file_name}
                        </Glance>
                      </span>
                    </>
                  )}
                </div>
              )}
            </div>
            <button className={s.link} onClick={() => setExpanded(!expanded)} aria-expanded={expanded}>
              {expanded ? 'Hide files' : 'Show files'}
            </button>
          </div>
          <p className={s.need}>{needLine(g.kind, g.field, ex)}</p>
          {ex && <Chips ex={ex} />}
          <p className={s.reason}>{n === 1 ? first.reason : first.reason.replace(/^[^:]*: /, '')}</p>
        </div>
      </div>

      {open && needsValue && (
        <div className={s.actions}>
          {suggestion?.value && (
            <div className={s.suggestion}>
              <span>
                Suggested: <strong>{suggestion.value}</strong> <span className="muted">{suggestion.why}</span>
              </span>
              <Button onClick={() => setAll({ accept_suggestion: true })}>
                Use for {n === 1 ? 'this file' : `all ${n}`}
              </Button>
            </div>
          )}
          <form
            className={s.valueForm}
            onSubmit={(e) => {
              e.preventDefault()
              if (value) setAll({ value })
            }}
          >
            {g.field === 'frame_type' || g.kind === 'classification_unknown' ? (
              <select
                aria-label="Frame type"
                value={value}
                onChange={(e) => setValue(e.target.value)}
                className={s.select}
              >
                <option value="">Choose a type…</option>
                {FRAME_TYPES.map(([v, label]) => (
                  <option key={v} value={v}>
                    {label}
                  </option>
                ))}
              </select>
            ) : (
              <input
                aria-label={FIELD_LABEL[g.field ?? ''] ?? 'Value'}
                placeholder={FIELD_LABEL[g.field ?? ''] ?? 'Value'}
                value={value}
                onChange={(e) => setValue(e.target.value)}
                className={s.input}
              />
            )}
            <Button type="submit" variant="primary" disabled={!value}>
              Set for {n === 1 ? 'this file' : `all ${n}`}
            </Button>
            <Button type="button" onClick={dismissAll}>
              Dismiss
            </Button>
          </form>
        </div>
      )}
      {open && (g.kind === 'bad_without_twin' || g.kind === 'ambiguous_master') && (
        <div className={s.actions}>
          <Button onClick={acknowledge}>Got it</Button>
        </div>
      )}
      {open && g.kind === 'frame_missing' && (
        <div className={s.actions}>
          <span className="muted">Put the file back and it clears itself, or accept that it’s gone.</span>
          <Button onClick={dismissAll}>Accept {n === 1 ? 'it’s' : 'they’re'} gone</Button>
        </div>
      )}
      {open && ex && ex.library_id != null && (ex.folder || glob) && (
        <div className={s.ignore}>
          {ex.folder && (
            <Button onClick={ignoreFolder} title={`Skip everything in ${where}`}>
              Ignore this folder
            </Button>
          )}
          {glob && (
            <Button onClick={ignoreLike} title={`Skip files named like ${glob} anywhere in ${ex.library}`}>
              Ignore files like this
            </Button>
          )}
          {glob && <span className={`${s.glob} mono muted`}>{glob}</span>}
        </div>
      )}
      {expanded && <FileList items={g.items} />}
    </li>
  )
}

/** The example frame, small; click for the close look. */
function Thumb({ sha, name }: { sha: string; name: string }) {
  const [failed, setFailed] = useState(false)
  return (
    <div className={s.thumb}>
      {failed ? (
        <span className={s.noThumb}>No preview</span>
      ) : (
        <Zoomable target={{ kind: 'sub', sha }} name={name}>
          <img src={glanceUrl(sha)} alt={name} loading="lazy" onError={() => setFailed(true)} />
        </Zoomable>
      )}
    </div>
  )
}

const DARKISH = new Set(['dark', 'bias', 'dark_flat', 'master_dark', 'master_bias', 'master_dark_flat'])

/** The example's header values, label: value; a missing one says so (in the warn colour). */
function Chips({ ex }: { ex: Example }) {
  const num = (v: number | null | undefined, unit = '') =>
    v == null ? null : `${signed(v, Number.isInteger(v) ? 0 : 1)}${unit}`
  const nights =
    ex.first_night && ex.last_night && ex.first_night !== ex.last_night
      ? `${shortDateText(ex.first_night)} – ${shortDateText(ex.last_night)}`
      : ex.night
        ? shortDateText(ex.night)
        : null
  const rows: [string, string | null, string[]][] = [
    ['Camera', ex.camera ?? null, ['camera']],
    ...(ex.telescope ? ([['Telescope', ex.telescope, ['telescope']]] as [string, string, string[]][]) : []),
    ['Exposure', num(ex.exptime_s, ' s'), ['exptime']],
    // darks and bias have no filter: not worth a "missing"
    ...(DARKISH.has(ex.frame_type) && !ex.filter
      ? []
      : ([['Filter', ex.filter ?? null, ['filter']]] as [string, string | null, string[]][])),
    ['Gain', num(ex.gain), ['gain']],
    ['Offset', num(ex.offset), ['offset']],
    ['Set temp', ex.set_temp_c == null ? null : tempText(ex.set_temp_c), ['set_temp']],
    ['Sensor temp', ex.ccd_temp_c == null ? null : tempText(ex.ccd_temp_c), ['ccd_temp']],
    [
      'Taken',
      ex.date_obs_utc
        ? `${shortDateText(ex.date_obs_utc)} ${new Date(ex.date_obs_utc).toISOString().slice(11, 16)} UTC`
        : null,
      ['date_obs'],
    ],
    ['Night', nights, []],
    ['Binning', ex.xbin == null ? null : `${ex.xbin}×${ex.ybin ?? ex.xbin}`, ['xbin', 'ybin']],
    ['Size', ex.width && ex.height ? `${ex.width}×${ex.height}` : null, []],
  ]
  return (
    <dl className={s.chips}>
      {rows.map(([label, v, fields]) => (
        <div
          key={label}
          className={`${s.chip} ${v == null ? s.missing : ''} ${fields.some((f) => ex.needs.includes(f)) ? s.needed : ''}`}
        >
          <dt>{label}</dt>
          <dd>{v ?? 'missing'}</dd>
        </div>
      ))}
    </dl>
  )
}

/** A group's files: a whole night can be thousands, so a slice at a time in a short scroll. */
function FileList({ items }: { items: ReconItem[] }) {
  const { visible, hasMore, more } = useProgressive(items, 100)
  return (
    <div className={s.files}>
      <ul>
        {visible.map((it) => (
          <li key={it.id} className="mono">
            {it.frame ? (
              <Glance sha={it.frame.sha256} label={fileName(it.frame.primary_path)}>
                {fileName(it.frame.primary_path)}
              </Glance>
            ) : (
              it.reason
            )}
          </li>
        ))}
      </ul>
      <LoadMore hasMore={hasMore} loading={false} onMore={more} />
    </div>
  )
}
