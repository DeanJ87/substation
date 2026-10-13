// "Ignore this sub" and "Ignore this folder" on the frame detail (T091). Undo lives in Settings → Ignored.
import { useQuery } from '@tanstack/react-query'
import { api, unwrap } from '../../api/client'
import { Button } from '../../components/ui'
import type { Frame } from '../datasets/queries'
import { useAddIgnore } from '../metadata/queries'
import s from './frames.module.css'

export function IgnoreActions({ frame }: { frame: Frame }) {
  const add = useAddIgnore()
  const libraries = useQuery({
    queryKey: ['libraries'],
    queryFn: async () => unwrap(await api.GET('/libraries')),
  })
  const copy = frame.copy_list.find((c) => c.present)
  const folder = copy && copy.path.includes('/') ? copy.path.slice(0, copy.path.lastIndexOf('/')) : null
  const libraryId = libraries.data?.find((l) => l.name === copy?.library)?.id ?? null

  if (frame.status === 'ignored')
    return <p className={`${s.note} muted`}>Ignored. Undo in Settings → Ignored.</p>

  return (
    <div className={s.ignoreActions}>
      <Button
        onClick={() =>
          add.mutate({
            rules: [{ kind: 'content', value: frame.sha256, note: 'ignored from the sub' }],
            sha256s: [frame.sha256],
          })
        }
      >
        Ignore this sub
      </Button>
      {folder && (
        <Button
          disabled={libraryId === null}
          onClick={() =>
            add.mutate({
              rules: [{ kind: 'folder', value: folder, library_id: libraryId }],
              sha256s: [frame.sha256],
            })
          }
          title={`${copy?.library}/${folder}/`}
        >
          Ignore its folder
        </Button>
      )}
    </div>
  )
}
