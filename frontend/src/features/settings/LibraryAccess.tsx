// Whether SubStation may write to each library, and the controls that need it (specs 011 and 013). A library mounted
// read-write is writable for the bin's deleting and for archiving; one mounted read-only is never written to. A
// control that can't be used for that reason stays in view, disabled, with the reason beside it and how to change it.
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useId } from 'react'
import { api, unwrap } from '../../api/client'
import type { components } from '../../api/schema'
import s from './settings.module.css'

export type Lib = components['schemas']['LibraryOut']
type Patch = components['schemas']['LibraryIn']

/** "Mounted read-only. Mount it read-write (SUBSTATION_LIBRARY_2_MODE=rw) to allow this." beside what it disables. */
export function ReadOnlyReason({ lib, id }: { lib: Lib; id?: string }) {
  if (lib.writable) return null
  return (
    <span id={id} className={s.reason}>
      {lib.read_only_reason ?? 'Mounted read-only. Mount it read-write to allow this.'}
    </span>
  )
}

/** "Mounted read-write" or "Mounted read-only", for the library's row. */
export function MountMode({ lib }: { lib: Lib }) {
  return (
    <span className={lib.writable ? s.mountRw : s.mountRo}>
      {lib.writable ? 'Mounted read-write' : 'Mounted read-only'}
    </span>
  )
}

export function usePatchLibrary() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async ({ id, body }: { id: number; body: Patch }) =>
      unwrap(await api.PATCH('/libraries/{id}', { params: { path: { id } }, body })),
    onSettled: () => {
      void qc.invalidateQueries({ queryKey: ['libraries'] })
      void qc.invalidateQueries({ queryKey: ['collection-files'] })
    },
    meta: { failed: "Couldn't change the library" },
  })
}

const ROLE_HELP: Record<string, string> = {
  '': 'Neither: its files stay where they are.',
  active: 'Active: new subs and work in progress. Archive moves its collections to its archive library.',
  archive: 'Archive: finished collections move here, and can be brought back.',
}

/** A library's role in archiving (spec 013) and, for an active one, its archive library. */
export function RoleControls({ lib, all, readOnly }: { lib: Lib; all: Lib[]; readOnly: boolean }) {
  const patch = usePatchLibrary()
  const reasonId = useId()
  const locked = readOnly || !lib.writable || patch.isPending
  const archives = all.filter((l) => l.role === 'archive' && l.id !== lib.id)
  return (
    <div className={s.roleControls}>
      <label>
        Role{' '}
        <select
          value={lib.role ?? ''}
          disabled={locked}
          aria-describedby={lib.writable ? undefined : reasonId}
          onChange={(e) =>
            patch.mutate({ id: lib.id, body: { role: e.target.value as 'active' | 'archive' | '' } })
          }
        >
          <option value="">Neither</option>
          <option value="active">Active</option>
          <option value="archive">Archive</option>
        </select>
      </label>
      {lib.role === 'active' && (
        <label>
          Archives to{' '}
          <select
            value={lib.archive_to ?? ''}
            disabled={locked || !archives.length}
            onChange={(e) =>
              patch.mutate({
                id: lib.id,
                body: { archive_to: e.target.value ? Number(e.target.value) : null },
              })
            }
          >
            <option value="">No archive</option>
            {archives.map((a) => (
              <option key={a.id} value={a.id} disabled={!a.writable}>
                {a.name}
                {a.writable ? '' : ' (read-only)'}
              </option>
            ))}
          </select>
        </label>
      )}
      <ReadOnlyReason lib={lib} id={reasonId} />
      {lib.writable && (
        <span className="muted">
          {ROLE_HELP[lib.role ?? '']}
          {lib.role === 'active' && !archives.length ? ' Set another library as an archive first.' : ''}
        </span>
      )}
    </div>
  )
}
