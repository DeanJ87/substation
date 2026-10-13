// Path pattern editor (T080; contracts/path-patterns.md). Type a pattern, see what it captures from real paths
// and which values it would change, then save. Saving re-reads matching files' values in the background.
import { useQuery } from '@tanstack/react-query'
import { useEffect, useState } from 'react'

function useDebounced(value: string, ms: number): string {
  const [v, setV] = useState(value)
  useEffect(() => {
    const t = window.setTimeout(() => setV(value), ms)
    return () => window.clearTimeout(t)
  }, [value, ms])
  return v
}
import { api, unwrap } from '../../api/client'
import { Button } from '../../components/ui'
import {
  FIELD_LABEL,
  previewPattern,
  useDeletePattern,
  usePatterns,
  useSavePattern,
  type PathPattern,
  type Preview,
} from '../metadata/queries'
import s from './settings.module.css'
import { useSort } from '../../components/sortable'
import { SettingsSection } from './SettingsSection'
import { LoadMore } from '../../components/LoadMore'
import { useProgressive } from '../../components/useProgressive'

const EXAMPLES = [
  // NINA names files with local clock time (summer time included), so leave the time to DATE-OBS
  {
    kind: 'filename',
    pattern: '{*}_{*}_{filter}_{temp}_{exposure}s_{seq}',
    note: 'NINA default file name',
  },
  { kind: 'folder', pattern: '{target}/{date}/{type}/', note: 'Target / night / type folders' },
  { kind: 'folder', pattern: '**/{object}/{*}/', note: 'Object anywhere in the tree' },
] as const

const TOKENS =
  '{target} {panel} {object} {filter} {exposure} {temp} {settemp} {gain} {offset} {bin} {type} {date} {time} {tz} {camera} {telescope} {seq} {*}'

type Draft = {
  kind: 'folder' | 'filename'
  pattern: string
  library_id: number | null
  scope_glob: string
  prefer_over_header: string[]
  priority: number
  enabled: boolean
}
const EMPTY: Draft = {
  kind: 'filename',
  pattern: '',
  library_id: null,
  scope_glob: '**',
  prefer_over_header: [],
  priority: 0,
  enabled: true,
}

export function PathPatterns() {
  const patterns = usePatterns()
  const libraries = useQuery({
    queryKey: ['libraries'],
    queryFn: async () => unwrap(await api.GET('/libraries')),
  })
  const save = useSavePattern()
  const remove = useDeletePattern()
  const [draft, setDraft] = useState<Draft>(EMPTY)
  const [editing, setEditing] = useState<number | undefined>()
  const [samples, setSamples] = useState('')
  // Live preview of the draft, debounced so typing doesn't flood the server
  const debouncedJson = useDebounced(JSON.stringify({ draft, samples }), 350)
  const debounced = JSON.parse(debouncedJson) as { draft: Draft; samples: string }
  const previewQ = useQuery({
    queryKey: ['pattern-preview', debouncedJson],
    enabled: debounced.draft.pattern.trim() !== '',
    retry: false,
    queryFn: () =>
      previewPattern(
        debounced.draft,
        debounced.samples
          .split('\n')
          .map((p) => p.trim())
          .filter(Boolean),
      ),
  })
  const hasPattern = draft.pattern.trim() !== ''
  const preview: Preview | null = hasPattern ? (previewQ.data ?? null) : null
  const previewError = hasPattern && previewQ.isError ? previewQ.error.message : null

  const set = <K extends keyof Draft>(k: K, v: Draft[K]) => setDraft((d) => ({ ...d, [k]: v }))
  const libName = (id: number | null) =>
    id === null ? 'All libraries' : (libraries.data?.find((l) => l.id === id)?.name ?? `#${id}`)

  function edit(p: PathPattern) {
    setEditing(p.id)
    setDraft({
      kind: p.kind,
      pattern: p.pattern,
      library_id: p.library_id ?? null,
      scope_glob: p.scope_glob ?? '**',
      prefer_over_header: p.prefer_over_header ?? [],
      priority: p.priority ?? 0,
      enabled: p.enabled ?? true,
    })
  }

  return (
    <SettingsSection
      id="patterns"
      title="Path patterns"
      meta={patterns.isSuccess ? patterns.data.length : undefined}
    >
      <p className="muted">
        Read values from folder and file names. Headers win unless “Prefer over the header” is ticked.
      </p>

      <ul className={s.patternList}>
        {(patterns.data ?? []).map((p) => (
          <li key={p.id} className={`${s.patternRow} ${p.id < 0 ? s.saving : ''}`}>
            <div>
              <div className="mono">
                <span className={s.kind}>{p.kind === 'folder' ? 'folder' : 'file name'}</span> {p.pattern}
              </div>
              <div className="muted">
                {p.id < 0 ? 'saving…' : `#${p.id}`} · {libName(p.library_id ?? null)}
                {p.scope_glob && p.scope_glob !== '**' ? ` · only ${p.scope_glob}` : ''} · fills{' '}
                {(p.fields ?? []).map((f) => FIELD_LABEL[f] ?? f).join(', ')}
                {(p.prefer_over_header ?? []).length > 0 &&
                  ` · beats the header for ${(p.prefer_over_header ?? []).map((f) => FIELD_LABEL[f] ?? f).join(', ')}`}
                {!p.enabled && ' · off'}
              </div>
              {p.error && <div className={s.error}>{p.error}</div>}
            </div>
            <div className={s.rowActions}>
              <Button onClick={() => edit(p)} disabled={p.id < 0}>
                Edit
              </Button>
              <Button variant="danger" onClick={() => remove.mutate(p.id)} disabled={p.id < 0}>
                Delete
              </Button>
            </div>
          </li>
        ))}
        {patterns.isSuccess && patterns.data.length === 0 && <li className="muted">No patterns.</li>}
      </ul>

      <form
        className={s.editor}
        onSubmit={(e) => {
          e.preventDefault()
          // the list changes at once and the editor empties; a failure brings the draft back
          const was = { draft, editing }
          save.mutate(
            { ...draft, id: editing },
            {
              onError: () => {
                setDraft(was.draft)
                setEditing(was.editing)
              },
            },
          )
          setDraft(EMPTY)
          setEditing(undefined)
        }}
      >
        <h3>{editing ? `Edit pattern #${editing}` : 'New pattern'}</h3>
        <div className={s.examples}>
          {EXAMPLES.map((ex) => (
            <button
              type="button"
              key={ex.pattern}
              className={s.chip}
              onClick={() => setDraft((d) => ({ ...d, kind: ex.kind, pattern: ex.pattern }))}
            >
              {ex.note}
            </button>
          ))}
        </div>
        <div className={s.grid}>
          <label>
            <span className="label">Matches</span>
            <select value={draft.kind} onChange={(e) => set('kind', e.target.value as Draft['kind'])}>
              <option value="filename">File name</option>
              <option value="folder">Folder path</option>
            </select>
          </label>
          <label className={s.wide}>
            <span className="label">Pattern</span>
            <input
              className="mono"
              value={draft.pattern}
              onChange={(e) => set('pattern', e.target.value)}
              placeholder={EXAMPLES[0].pattern}
              spellCheck={false}
            />
            <span className={s.hint}>{TOKENS}</span>
          </label>
          <label>
            <span className="label">Library</span>
            <select
              value={draft.library_id ?? ''}
              onChange={(e) => set('library_id', e.target.value ? Number(e.target.value) : null)}
            >
              <option value="">All libraries</option>
              {(libraries.data ?? []).map((l) => (
                <option key={l.id} value={l.id}>
                  {l.name}
                </option>
              ))}
            </select>
          </label>
          <label>
            <span className="label">Only paths matching</span>
            <input
              className="mono"
              value={draft.scope_glob}
              onChange={(e) => set('scope_glob', e.target.value)}
            />
          </label>
          <label>
            <span className="label">Priority</span>
            <input
              type="number"
              value={draft.priority}
              onChange={(e) => set('priority', Number(e.target.value))}
            />
          </label>
        </div>
        {preview && preview.fields.length > 0 && (
          <fieldset className={s.prefer}>
            <legend className="label">Prefer over the header for</legend>
            {preview.fields.map((f) => (
              <label key={f}>
                <input
                  type="checkbox"
                  checked={draft.prefer_over_header.includes(f)}
                  onChange={(e) =>
                    set(
                      'prefer_over_header',
                      e.target.checked
                        ? [...draft.prefer_over_header, f]
                        : draft.prefer_over_header.filter((x) => x !== f),
                    )
                  }
                />{' '}
                {FIELD_LABEL[f] ?? f}
              </label>
            ))}
          </fieldset>
        )}
        <label className={s.wide}>
          <span className="label">Test paths (one per line)</span>
          <textarea
            className="mono"
            rows={3}
            value={samples}
            onChange={(e) => setSamples(e.target.value)}
            placeholder="Leave empty to test on known files"
          />
        </label>

        {previewError && (
          <p role="alert" className={s.error}>
            {previewError}
          </p>
        )}
        {preview && <PreviewView p={preview} />}

        <div className={s.rowActions}>
          <Button type="submit" variant="primary" disabled={!draft.pattern || !!previewError}>
            {editing ? 'Save changes' : 'Add pattern'}
          </Button>
          {editing && (
            <Button
              type="button"
              onClick={() => {
                setEditing(undefined)
                setDraft(EMPTY)
              }}
            >
              Cancel
            </Button>
          )}
        </div>
      </form>
    </SettingsSection>
  )
}

function PreviewView({ p }: { p: Preview }) {
  const { sorted, th, sort } = useSort(p.samples, {
    path: (x) => x.path,
    captures: (x) => (x.matched ? Object.values(x.values).join(' ') : null),
  })
  // sorted first, then a slice at a time; a new preview or sort starts at the top
  const { visible, hasMore, more } = useProgressive(
    sorted,
    60,
    `${p.samples.length}|${sort?.key}|${sort?.desc}`,
  )
  return (
    <div className={s.preview}>
      <p>
        Fills <strong>{p.fields.map((f) => FIELD_LABEL[f] ?? f).join(', ')}</strong>. Matches{' '}
        <strong>{p.matching_files}</strong> known file{p.matching_files === 1 ? '' : 's'}.
      </p>
      <div className={s.scrollPane}>
        <table className={s.previewTable}>
          <thead>
            <tr>
              {th('path', 'Path')}
              {th('captures', 'Captures')}
            </tr>
          </thead>
          <tbody>
            {visible.map((smp) => (
              <tr key={smp.path}>
                <td className="mono">{smp.path}</td>
                <td className={smp.matched ? undefined : 'muted'}>
                  {smp.matched
                    ? Object.entries(smp.values)
                        .map(([k, v]) => `${FIELD_LABEL[k] ?? k} = ${String(v)}`)
                        .join(' · ')
                    : 'no match'}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        <LoadMore hasMore={hasMore} loading={false} onMore={more} />
      </div>
      {p.would_change.length > 0 && (
        <>
          <p>
            Differs for {p.would_change.length}
            {p.would_change.length === 50 ? '+' : ''} file{p.would_change.length === 1 ? '' : 's'}:
          </p>
          <ul className={s.changes}>
            {p.would_change.slice(0, 8).map((w) => (
              <li key={w.sha256}>
                <span className="mono">{w.path.split('/').pop()}</span>:{' '}
                {w.changes
                  .map((c) => `${FIELD_LABEL[c.field] ?? c.field} ${c.current ?? '(none)'} → ${c.new}`)
                  .join(', ')}
              </li>
            ))}
          </ul>
        </>
      )}
    </div>
  )
}
