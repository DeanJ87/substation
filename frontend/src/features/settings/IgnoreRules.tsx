// Ignored folders, file names and subs (T091), with undo. Ignored content stays ignored wherever it appears.
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { api, unwrap } from '../../api/client'
import { LoadMore } from '../../components/LoadMore'
import { toast } from '../../components/Toasts'
import { Button, ConfirmButton, Skeleton } from '../../components/ui'
import { binMessage } from './Bin'
import { useAddIgnore, useIgnoreRules, useUndoIgnore, type IgnoreRule } from '../metadata/queries'
import s from './settings.module.css'
import { SettingsSection } from './SettingsSection'

const KIND_TEXT: Record<string, string> = { folder: 'Folder', glob: 'File names', content: 'Sub' }

function describe(r: IgnoreRule) {
  if (r.kind === 'content') return <span className="mono">{r.value.slice(0, 16)}…</span>
  return <span className="mono">{r.kind === 'folder' ? `${r.value}/` : r.value}</span>
}

export function IgnoreRules() {
  const [sort, setSort] = useState<'newest' | 'kind' | 'files'>('newest')
  const rules = useIgnoreRules(sort)
  const rows = rules.data?.pages.flat() ?? []
  const add = useAddIgnore()
  const undo = useUndoIgnore()
  const qc = useQueryClient()
  // the files a rule sets aside (e.g. 8-bit captures) into the bin (spec 011)
  const binRule = useMutation({
    mutationFn: async (id: number) =>
      unwrap(await api.POST('/ignore-rules/{id}/bin', { params: { path: { id } } })),
    onSuccess: (r) => toast(binMessage(r)),
    onSettled: () => void qc.invalidateQueries(),
    meta: { failed: "Couldn't bin the files" },
  })
  const libraries = useQuery({
    queryKey: ['libraries'],
    queryFn: async () => unwrap(await api.GET('/libraries')),
  })
  const [kind, setKind] = useState<'folder' | 'glob'>('folder')
  const [value, setValue] = useState('')
  const [library, setLibrary] = useState<number | null>(null)
  const libName = (id: number | null | undefined) =>
    id == null ? 'every library' : (libraries.data?.find((l) => l.id === id)?.name ?? `#${id}`)

  return (
    <SettingsSection
      id="ignored"
      title="Ignored"
      meta={rules.isSuccess ? `${rows.length}${rules.hasNextPage ? '+' : ''}` : undefined}
    >
      <p className="muted">Ignored files are skipped and excluded from datasets.</p>
      <div className={s.rowActions} role="group" aria-label="Sort rules">
        <span className="muted">Sort</span>
        {(
          [
            ['newest', 'Newest'],
            ['kind', 'Kind'],
            ['files', 'Files held back'],
          ] as const
        ).map(([k, label]) => (
          <button
            key={k}
            type="button"
            className={s.sortPill}
            aria-pressed={sort === k}
            onClick={() => setSort(k)}
          >
            {label}
          </button>
        ))}
      </div>
      <div className={s.scrollPane}>
        <ul className={s.patternList}>
          {rules.isPending &&
            [0, 1, 2].map((i) => (
              <li key={i} className={s.patternRow}>
                <Skeleton height={34} />
              </li>
            ))}
          {rows.map((r) => (
            <li key={r.id} className={`${s.patternRow} ${r.id < 0 ? s.saving : ''}`}>
              <div>
                <div>
                  <span className={s.kind}>{KIND_TEXT[r.kind]}</span> {describe(r)}
                </div>
                <div className="muted">
                  {r.kind === 'content' ? '' : `In ${libName(r.library_id)} · `}
                  {r.id < 0 ? (
                    'saving…'
                  ) : (
                    <>
                      {r.matches ?? 0} file{r.matches === 1 ? '' : 's'} known · by {r.created_by ?? 'someone'}{' '}
                      on {r.created_at ? new Date(r.created_at).toLocaleDateString('en-GB') : ''}
                    </>
                  )}
                  {r.note && ` · ${r.note}`}
                </div>
              </div>
              <span className={s.rowActions}>
                {(r.matches ?? 0) > 0 && (
                  <ConfirmButton
                    question={<>Bin these {r.matches} files?</>}
                    confirm="Bin them"
                    onConfirm={() => binRule.mutate(r.id)}
                  >
                    Bin these files
                  </ConfirmButton>
                )}
                <Button onClick={() => undo.mutate(r.id)} disabled={r.id < 0}>
                  Undo
                </Button>
              </span>
            </li>
          ))}
          {rules.isSuccess && rows.length === 0 && <li className="muted">Nothing is ignored.</li>}
        </ul>
        <LoadMore
          hasMore={!!rules.hasNextPage}
          loading={rules.isFetchingNextPage}
          onMore={() => void rules.fetchNextPage()}
        />
      </div>
      <form
        className={s.inlineForm}
        onSubmit={(e) => {
          e.preventDefault()
          if (!value.trim()) return
          // the rule shows at once; the box clears for the next one, and gets the text back if it fails
          const v = value.trim()
          add.mutate(
            { rules: [{ kind, value: v, library_id: library }] },
            { onError: () => setValue((cur) => cur || v) },
          )
          setValue('')
        }}
      >
        <select
          aria-label="Ignore what"
          value={kind}
          onChange={(e) => setKind(e.target.value as 'folder' | 'glob')}
        >
          <option value="folder">Folder</option>
          <option value="glob">File names like</option>
        </select>
        <input
          aria-label={kind === 'folder' ? 'Folder' : 'File name pattern'}
          className="mono"
          value={value}
          onChange={(e) => setValue(e.target.value)}
          placeholder={kind === 'folder' ? '2026-09-28/TEST' : '*_test_*'}
        />
        <select
          aria-label="Library"
          value={library ?? ''}
          onChange={(e) => setLibrary(e.target.value ? Number(e.target.value) : null)}
        >
          <option value="">Every library</option>
          {(libraries.data ?? []).map((l) => (
            <option key={l.id} value={l.id}>
              {l.name}
            </option>
          ))}
        </select>
        <Button type="submit" disabled={!value.trim()}>
          Ignore
        </Button>
      </form>
    </SettingsSection>
  )
}
