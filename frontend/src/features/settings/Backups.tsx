// Database backups (spec 014): a nightly .tar.gz of everything SubStation knows (not your image files), kept in a
// folder you choose; back up now, download one, or restore one.
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { api, unwrap } from '../../api/client'
import { toast } from '../../components/Toasts'
import { Button } from '../../components/ui'
import { bytes, dateTimeText } from '../format'
import { useDraft } from './draft'
import v from '../v2/v2.module.css'
import s from './settings.module.css'
import { SettingsSection } from './SettingsSection'

const when = (iso: string) => dateTimeText(iso)

export function Backups() {
  const qc = useQueryClient()
  const { draft, set, readOnly } = useDraft()
  const [restoring, setRestoring] = useState<string | null>(null)
  const [typed, setTyped] = useState('')
  const list = useQuery({
    queryKey: ['backups'],
    queryFn: async () => unwrap(await api.GET('/backups')),
    refetchInterval: (q) => (q.state.data?.running ? 3000 : false),
  })
  const now = useMutation({
    mutationFn: async () => unwrap(await api.POST('/backups')),
    onSuccess: () => toast('Backing up'),
    onSettled: () => void qc.invalidateQueries({ queryKey: ['backups'] }),
    meta: { failed: "Couldn't start the backup" },
  })
  const restore = useMutation({
    mutationFn: async (name: string) =>
      unwrap(
        await api.POST('/backups/{name}/restore', { params: { path: { name } }, body: { confirm: typed } }),
      ),
    onSuccess: (r) => {
      toast(r.note || 'Restoring')
      setRestoring(null)
      setTyped('')
    },
    onSettled: () => void qc.invalidateQueries({ queryKey: ['backups'] }),
    meta: { failed: "Couldn't start the restore" },
  })
  if (!draft) return null
  const b = draft.backup ?? { enabled: true, time: '03:30', keep: 14, folder: '' }
  const d = list.data
  return (
    <SettingsSection
      id="backups"
      title="Backups"
      meta={d ? d.backups.length : undefined}
      help={
        <>
          Everything SubStation knows: libraries, files, grades, masters, settings and users, as one .tar.gz.
          Your image files aren't in it. Restoring replaces the whole database with the backup.
        </>
      }
    >
      <div className={s.backupRow}>
        <label>
          <input
            type="checkbox"
            checked={b.enabled}
            disabled={readOnly}
            onChange={(e) => set('backup', 'enabled', e.target.checked)}
          />{' '}
          Back up every day at{' '}
          <input
            type="time"
            value={b.time}
            disabled={readOnly || !b.enabled}
            aria-label="Backup time"
            onChange={(e) => e.target.value && set('backup', 'time', e.target.value)}
          />
        </label>
      </div>
      <div className={s.backupRow}>
        <label>
          Keep the newest{' '}
          <input
            className={s.num}
            type="number"
            min={1}
            max={365}
            value={b.keep}
            disabled={readOnly}
            aria-label="Backups to keep"
            onChange={(e) => e.target.value !== '' && set('backup', 'keep', Number(e.target.value))}
          />{' '}
          backups
        </label>
      </div>
      <div className={s.backupRow}>
        <label>
          Folder{' '}
          <input
            className={`${s.mono} ${s.backupFolder}`}
            placeholder={d?.folder ?? '/data/substation/backups'}
            value={b.folder}
            disabled={readOnly}
            aria-label="Backup folder"
            onChange={(e) => set('backup', 'folder', e.target.value)}
          />
        </label>
        <span className="muted">
          A folder inside the containers; empty is the station's own. Mount another to keep backups elsewhere.
        </span>
      </div>
      {d && !d.writable && (
        <p role="alert" className={s.error}>
          SubStation can't write to {d.folder}. Check it's mounted and owned by user 1000.
        </p>
      )}
      <div className={s.backupRow}>
        <Button
          variant="primary"
          disabled={readOnly || d?.running || now.isPending}
          onClick={() => now.mutate()}
        >
          {d?.running ? 'Working…' : 'Back up now'}
        </Button>
        {d && <span className="muted">In {d.folder}</span>}
      </div>
      {d && d.backups.length === 0 && <p className="muted">No backups yet.</p>}
      {d && d.backups.length > 0 && (
        <ul className={s.backupList}>
          {d.backups.map((x) => {
            const size = bytes(x.size_bytes)
            return (
              <li key={x.name} className={s.backupItem}>
                <div>
                  <strong>{when(x.made_at)}</strong>
                  <div className={`muted ${s.mono}`}>
                    {x.name} · {size.value} {size.unit}
                  </div>
                </div>
                <div className={s.backupRow}>
                  <a
                    className={v.pill}
                    href={`/api/v1/backups/${encodeURIComponent(x.name)}/download`}
                    download
                  >
                    Download
                  </a>
                  {!readOnly && (
                    <Button onClick={() => setRestoring(restoring === x.name ? null : x.name)}>
                      Restore…
                    </Button>
                  )}
                </div>
                {restoring === x.name && (
                  <div className={s.backupConfirm}>
                    <span>
                      This replaces everything SubStation knows with this backup. New work pauses while it
                      runs. Type <strong>restore</strong> to go ahead:
                    </span>
                    <input
                      value={typed}
                      aria-label="Type restore to confirm"
                      onChange={(e) => setTyped(e.target.value)}
                    />
                    <Button
                      variant="danger"
                      disabled={typed.trim().toLowerCase() !== 'restore' || restore.isPending}
                      onClick={() => restore.mutate(x.name)}
                    >
                      Restore this backup
                    </Button>
                  </div>
                )}
              </li>
            )
          })}
        </ul>
      )}
    </SettingsSection>
  )
}
