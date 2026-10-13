// The bin (spec 011, owner 2026-10-13): binned files wait in their library's quarantine folder, then are deleted
// for good; rejected subs bin themselves after a while. Libraries SubStation may not delete in only hide files.
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, unwrap } from '../../api/client'
import { toast } from '../../components/Toasts'
import { Button } from '../../components/ui'
import { bytes } from '../format'
import { useDraft } from './draft'
import s from './settings.module.css'
import { SettingsSection } from './SettingsSection'

const day = (iso: string | null | undefined) =>
  iso ? new Date(iso).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' }) : ''

export function Bin() {
  const qc = useQueryClient()
  const { draft, set, readOnly } = useDraft()
  const libs = useQuery({ queryKey: ['libraries'], queryFn: async () => unwrap(await api.GET('/libraries')) })
  const bin = useQuery({ queryKey: ['bin'], queryFn: async () => unwrap(await api.GET('/bin')) })
  const allow = useMutation({
    mutationFn: async ({ id, on }: { id: number; on: boolean }) =>
      unwrap(await api.PATCH('/libraries/{id}', { params: { path: { id } }, body: { allow_delete: on } })),
    onSettled: () => void qc.invalidateQueries({ queryKey: ['libraries'] }),
    meta: { failed: "Couldn't change the library" },
  })
  const restore = useMutation({
    mutationFn: async (sha: string) =>
      unwrap(await api.POST('/bin/restore', { body: { sha256s: [sha], reason: '' } })),
    onSuccess: (r) =>
      toast(r.restored ? 'Restored.' : "Couldn't restore it: something else is in its old place."),
    onSettled: () => void qc.invalidateQueries(),
    meta: { failed: "Couldn't restore the file" },
  })
  const tidy = useMutation({
    mutationFn: async () => unwrap(await api.POST('/bin/tidy')),
    onSuccess: () => toast('Tidying the bin.'),
    meta: { failed: "Couldn't start the tidy" },
  })
  if (!draft) return null
  const b = draft.bin ?? { auto_bin_rejected_days: 30, purge_after_days: 30 }
  const d = bin.data
  const q = bytes(d?.bytes_in_quarantine)
  return (
    <SettingsSection id="bin" title="Bin" meta={d ? d.total : undefined}>
      <p className="muted">
        Binned files leave SubStation at once. In a library SubStation may delete in, they move to a hidden{' '}
        <span className={s.mono}>.substation-quarantine</span> folder there and are deleted for good later;
        elsewhere they're only hidden. Their records stay, so your history still counts them.
      </p>
      <div className={s.inline}>
        <label>
          Bin rejected subs after{' '}
          <input
            className={s.num}
            type="number"
            min={0}
            step={1}
            value={b.auto_bin_rejected_days}
            disabled={readOnly}
            aria-label="Bin rejected subs after (days)"
            onChange={(e) =>
              e.target.value !== '' && set('bin', 'auto_bin_rejected_days', Number(e.target.value))
            }
          />{' '}
          days <span className="muted">(0: never)</span>
        </label>
      </div>
      <div className={s.inline}>
        <label>
          Delete binned files after{' '}
          <input
            className={s.num}
            type="number"
            min={1}
            step={1}
            value={b.purge_after_days}
            disabled={readOnly}
            aria-label="Delete binned files after (days)"
            onChange={(e) => e.target.value !== '' && set('bin', 'purge_after_days', Number(e.target.value))}
          />{' '}
          days
        </label>
      </div>
      <strong>Libraries</strong>
      <ul className={s.patternList}>
        {(libs.data ?? [])
          .filter((l) => l.enabled)
          .map((l) => (
            <li key={l.id} className={s.patternRow}>
              <div>
                <strong className={s.mono}>{l.mount_path}</strong>
                <div className="muted">
                  {!l.writable
                    ? 'Mounted read-only: binned files are hidden, never moved or deleted.'
                    : l.allow_delete
                      ? 'Binned files move to quarantine here, then are deleted.'
                      : 'Binned files are only hidden here.'}
                </div>
              </div>
              <div className={s.rowActions}>
                <label>
                  <input
                    type="checkbox"
                    checked={l.allow_delete}
                    disabled={readOnly || !l.writable || allow.isPending}
                    onChange={(e) => allow.mutate({ id: l.id, on: e.target.checked })}
                  />{' '}
                  SubStation may delete files here
                </label>
              </div>
            </li>
          ))}
      </ul>
      <strong>In the bin</strong>
      {d && (
        <p className="muted">
          {d.total.toLocaleString('en-GB')} file{d.total === 1 ? '' : 's'}: {d.moved.toLocaleString('en-GB')}{' '}
          in quarantine ({q.value} {q.unit}), {d.hidden.toLocaleString('en-GB')} only hidden ·{' '}
          {d.deleted.toLocaleString('en-GB')} deleted so far
        </p>
      )}
      <ul className={s.patternList}>
        {(d?.rows ?? []).map((r) => (
          <li key={r.sha256} className={s.patternRow}>
            <div>
              <strong className={s.mono}>{r.name}</strong>
              <div className="muted">
                {r.reason}
                {r.binned_at ? ` · binned ${day(r.binned_at)}` : ''}
                {r.purge_after ? ` · deleted ${day(r.purge_after)}` : ' · hidden, not deleted'}
              </div>
            </div>
            <div className={s.rowActions}>
              <Button disabled={readOnly || restore.isPending} onClick={() => restore.mutate(r.sha256)}>
                Restore
              </Button>
            </div>
          </li>
        ))}
      </ul>
      <Button disabled={readOnly || tidy.isPending} onClick={() => tidy.mutate()}>
        Tidy now
      </Button>
    </SettingsSection>
  )
}

type BinResult = { binned: number; moved: number; hidden: number }

/** "3 binned: 2 to quarantine, 1 hidden (its library is read-only to SubStation)." */
export function binMessage(r: BinResult): string {
  if (!r.binned) return 'Nothing to bin.'
  const parts = [
    r.moved ? `${r.moved} to quarantine` : '',
    r.hidden ? `${r.hidden} only hidden (SubStation may not delete there)` : '',
  ].filter(Boolean)
  return `${r.binned} binned: ${parts.join(', ')}.`
}

/** Bin files by hand, from wherever they're listed. */
export function useBinFiles() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (sha256s: string[]) =>
      unwrap(await api.POST('/bin', { body: { sha256s, reason: '' } })),
    onSuccess: (r) => toast(binMessage(r)),
    onSettled: () => void qc.invalidateQueries(),
    meta: { failed: "Couldn't bin the files" },
  })
}
