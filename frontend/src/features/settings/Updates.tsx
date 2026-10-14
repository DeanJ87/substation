// Updates (005-DR-23): SubStation notices a newer build, waits until no stack is running, then asks Portainer to
// redeploy it. No scripts and nothing logging in to the NAS.
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, unwrap } from '../../api/client'
import { Button } from '../../components/ui'
import s from './settings.module.css'
import { SettingsSection } from './SettingsSection'
import { useDraft } from './draft'

const when = (iso: string | null | undefined) =>
  iso
    ? new Date(iso).toLocaleString('en-GB', {
        day: 'numeric',
        month: 'short',
        hour: '2-digit',
        minute: '2-digit',
      })
    : ''

const STATE: Record<string, string> = {
  draining: 'Waiting to update',
  deploying: 'Updating: Portainer is redeploying',
  failed: "The last update didn't finish",
}

export function Updates() {
  const qc = useQueryClient()
  const { readOnly } = useDraft()
  const u = useQuery({
    queryKey: ['updates'],
    queryFn: async () => unwrap(await api.GET('/settings/updates')),
    refetchInterval: 15_000,
  })
  const done = (data: unknown) => qc.setQueryData(['updates'], data)
  const auto = useMutation({
    mutationFn: async (on: boolean) => unwrap(await api.PATCH('/settings/updates', { body: { auto: on } })),
    onSuccess: done,
    meta: { failed: "Couldn't change automatic updates" },
  })
  const now = useMutation({
    mutationFn: async () => unwrap(await api.POST('/settings/updates/now')),
    onSuccess: done,
    meta: { failed: "Couldn't start the update" },
  })
  const cancel = useMutation({
    mutationFn: async () => unwrap(await api.POST('/settings/updates/cancel')),
    onSuccess: done,
    meta: { failed: "Couldn't stop the update" },
  })
  const d = u.data
  if (!d) return null
  return (
    <SettingsSection id="updates" title="Updates" meta={d.running || undefined}>
      {!d.configured ? (
        <p className="muted">
          Updates are off: set <span className={s.mono}>SUBSTATION_UPDATE_WEBHOOK</span> (the stack's webhook
          in Portainer) and <span className={s.mono}>SUBSTATION_UPDATE_REPO</span> on the stack to turn them
          on.
        </p>
      ) : (
        <>
          <p>
            Running <span className={s.mono}>{d.running}</span> from{' '}
            <span className={s.mono}>{d.branch}</span>
            {d.last?.at ? `, updated ${when(d.last.at as string)}` : ''}.{' '}
            {d.available && d.latest ? (
              <>
                A newer build is ready: <span className={s.mono}>{d.latest.sha.slice(0, 7)}</span> “
                {d.latest.title}”, built {when(d.latest.built_at)}.
              </>
            ) : (
              <span className="muted">
                Up to date{d.checked_at ? ` (checked ${when(d.checked_at)})` : ''}.
              </span>
            )}
          </p>
          {d.state && (
            <p>
              <strong>{STATE[d.state] ?? d.state}</strong>
              {d.reason ? `: ${d.reason}` : '.'}
            </p>
          )}
          {d.check_error && <p className="muted">{d.check_error}</p>}
          <div className={s.inline}>
            <label>
              <input
                type="checkbox"
                checked={d.auto}
                disabled={readOnly}
                onChange={(e) => auto.mutate(e.target.checked)}
              />{' '}
              Update automatically once no stack is running
            </label>
          </div>
          <div className={s.inline}>
            {d.state === 'draining' ? (
              <Button disabled={readOnly || cancel.isPending} onClick={() => cancel.mutate()}>
                Don't update now
              </Button>
            ) : (
              <Button
                variant={d.available ? 'primary' : 'default'}
                disabled={readOnly || now.isPending || d.state === 'deploying'}
                onClick={() => now.mutate()}
              >
                {d.available ? 'Update now' : 'Check now'}
              </Button>
            )}
          </div>
          <p className="muted">
            While it waits, the queue is paused so no new stack starts; running stacks finish first. The queue
            resumes once the new version is up.
          </p>
        </>
      )}
    </SettingsSection>
  )
}
