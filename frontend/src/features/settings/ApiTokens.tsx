// Personal API tokens (spec 020, 020-FR-011): for the renderer app to read finished projects. A token is shown once,
// when it's made, and stored only hashed; it can only read the render API, and can be revoked at any time.
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { api, unwrap } from '../../api/client'
import type { components } from '../../api/schema'
import { toast } from '../../components/Toasts'
import { Button, ConfirmButton } from '../../components/ui'
import f from '../finished/finished.module.css'
import v from '../v2/v2.module.css'
import { useSettings } from './draft'
import s from './settings.module.css'
import { SettingsSection } from './SettingsSection'
import { dateTimeText } from '../format'

type Token = components['schemas']['TokenOut']

const when = (iso: string | null | undefined, never = 'never') => (iso ? dateTimeText(iso) : never)

const state = (t: Token) => (t.revoked_at ? 'Revoked' : t.active ? 'Active' : 'Expired')

export function ApiTokens() {
  const qc = useQueryClient()
  const settings = useSettings()
  const admin = !!settings.data?.can_edit
  const [name, setName] = useState('')
  const [expires, setExpires] = useState('')
  const [made, setMade] = useState<{ name: string; secret: string } | null>(null)
  const list = useQuery({
    queryKey: ['tokens'],
    enabled: admin,
    queryFn: async () => unwrap(await api.GET('/tokens')),
  })
  const create = useMutation({
    mutationFn: async (body: { name: string; expires_at: string | null }) =>
      unwrap(await api.POST('/tokens', { body })),
    onSuccess: (r) => {
      setMade({ name: r.token.name, secret: r.secret })
      setName('')
      setExpires('')
    },
    onSettled: () => void qc.invalidateQueries({ queryKey: ['tokens'] }),
    meta: { failed: "Couldn't create the token" },
  })
  const revoke = useMutation({
    mutationFn: async (id: number) =>
      unwrap(await api.POST('/tokens/{id}/revoke', { params: { path: { id } } })),
    onSuccess: (t) => toast(`${t.name} revoked.`),
    onSettled: () => void qc.invalidateQueries({ queryKey: ['tokens'] }),
    meta: { failed: "Couldn't revoke the token" },
  })
  const tokens = list.data ?? []
  const origin = window.location.origin
  return (
    <SettingsSection
      id="tokens"
      title="API tokens"
      meta={list.isSuccess ? tokens.length : undefined}
      help={
        <>
          A token lets another app, such as the renderer, read your finished projects and their files. It
          can't sign in, change anything or reach the rest of SubStation. Make one per app, so you can revoke
          one without the others.
        </>
      }
    >
      {!admin ? null : (
        <>
          <form
            className={s.formGrid}
            onSubmit={(e) => {
              e.preventDefault()
              if (!name.trim()) return
              // an expiry date lasts to the end of that day, here
              create.mutate({
                name: name.trim(),
                expires_at: expires ? new Date(`${expires}T23:59:59`).toISOString() : null,
              })
            }}
          >
            <label className={s.inline}>
              Name
              <input
                value={name}
                maxLength={100}
                placeholder="e.g. dean0 render"
                onChange={(e) => setName(e.target.value)}
              />
            </label>
            <label className={s.inline}>
              Expires
              <input type="date" value={expires} onChange={(e) => setExpires(e.target.value)} />
              <span className="muted">(optional)</span>
            </label>
            <Button type="submit" variant="primary" disabled={!name.trim() || create.isPending}>
              Create token
            </Button>
          </form>

          {made && (
            <div className={f.secret} role="region" aria-label="New token">
              <strong>Copy this token now. You won't see it again.</strong>
              <div className={f.row}>
                <input
                  className={`${f.input} ${f.secretValue}`}
                  readOnly
                  value={made.secret}
                  aria-label={`Token for ${made.name}`}
                  onFocus={(e) => e.target.select()}
                />
                <Button
                  onClick={() =>
                    navigator.clipboard?.writeText(made.secret).then(
                      () => toast('Token copied'),
                      () => toast("Couldn't copy the token: select it and copy it yourself"),
                    )
                  }
                >
                  Copy
                </Button>
              </div>
              <div className="muted">
                The app sends it in an Authorization header with each request to the render API, for example:
              </div>
              <pre className={f.code}>
                {`curl -H "Authorization: Bearer ${made.secret}" \\\n  ${origin}/api/v1/render/projects`}
              </pre>
              <div>
                <Button onClick={() => setMade(null)}>I've copied it</Button>
              </div>
            </div>
          )}

          {list.isError ? (
            <p className={s.error}>{list.error.message}</p>
          ) : list.isSuccess && !tokens.length ? (
            <p className="muted">No tokens yet.</p>
          ) : (
            tokens.length > 0 && (
              <div className={f.scroll}>
                <table className={s.table}>
                  <thead>
                    <tr>
                      <th>Name</th>
                      <th>Token</th>
                      <th>Created</th>
                      <th>Last used</th>
                      <th>Expires</th>
                      <th>Status</th>
                      <th>
                        <span className="visually-hidden">Actions</span>
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {tokens.map((t) => (
                      <tr key={t.id}>
                        <td>
                          <strong>{t.name}</strong>
                        </td>
                        <td className={s.mono}>…{t.hint}</td>
                        <td>{when(t.created_at)}</td>
                        <td>{when(t.last_used_at)}</td>
                        <td>{when(t.expires_at, 'no expiry')}</td>
                        <td className={t.active ? v.ok : 'muted'}>
                          {state(t)}
                          {t.revoked_at && <div className="muted">{when(t.revoked_at)}</div>}
                        </td>
                        <td>
                          {t.active && (
                            <ConfirmButton
                              question={`Revoke ${t.name}? Apps using it stop working at once.`}
                              confirm="Revoke"
                              onConfirm={() => revoke.mutate(t.id)}
                            >
                              Revoke
                            </ConfirmButton>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )
          )}
        </>
      )}
    </SettingsSection>
  )
}
