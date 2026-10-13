// Rigs (spec 006 FR-001; design v2 A4): detected from TELESCOP, INSTRUME and FOCALLEN. Rename, or merge two that
// are the same equipment written differently by different capture software.
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { api, unwrap } from '../../api/client'
import { optimistic, patchItems, type Patch } from '../../api/optimistic'
import type { components } from '../../api/schema'
import { Button } from '../../components/ui'
import { tempId } from '../metadata/queries'
import s from './settings.module.css'
import { SettingsSection } from './SettingsSection'

export function Rigs() {
  const qc = useQueryClient()
  const rigs = useQuery({ queryKey: ['rigs'], queryFn: async () => unwrap(await api.GET('/rigs')) })
  const sugg = useQuery({
    queryKey: ['rig-suggestions'],
    queryFn: async () => unwrap(await api.GET('/rigs/suggestions')),
  })
  type Rig = components['schemas']['RigOut']
  type Mount = 'equatorial' | 'altaz' | 'tracker' | 'smart' | ''
  // what a rig change touches elsewhere; refreshed once the server answers
  const elsewhere = () => (['rig-suggestions', 'library', 'collection', 'dataset'] as const).map((k) => [k])
  const patchRig = (id: number, change: object): Patch[] => [
    [
      ['rigs'],
      (old) =>
        patchItems<Rig>(
          old,
          (r) => r.id === id,
          (r) => ({ ...r, ...change }),
        ),
    ],
  ]
  // rig edits run in order, whichever control made them, so the last one wins
  const edit = useMutation({
    scope: { id: 'rigs' },
    mutationFn: async ({ id, ...body }: { id: number } & components['schemas']['RigPatch']) =>
      unwrap(await api.PATCH('/rigs/{id}', { params: { path: { id } }, body })),
    ...optimistic(qc, ({ id, ...change }) => patchRig(id, change), elsewhere),
    meta: { failed: "Couldn't change the rig" },
  })
  const [draft, setDraft] = useState<{
    name: string
    telescope: string
    camera: string
    focal: string
    mount: Mount
  } | null>(null)
  type RigIn = components['schemas']['RigIn']
  const add = useMutation({
    mutationFn: async (body: RigIn) => unwrap(await api.POST('/rigs', { body })),
    ...optimistic(
      qc,
      (body: RigIn) => [
        [
          ['rigs'],
          (old) =>
            old && [
              ...(old as Rig[]),
              {
                ...body,
                focal_mm: body.focal_mm ?? null,
                id: tempId(),
                calibration: 'masters',
                image_scale: null,
                datasets: 0,
                sessions: 0,
              },
            ],
        ],
      ],
      elsewhere,
    ),
    meta: { failed: "Couldn't add the rig" },
  })
  const merge = useMutation({
    mutationFn: async ({ id, into }: { id: number; into: number }) =>
      unwrap(await api.POST('/rigs/{id}/merge', { params: { path: { id } }, body: { into } })),
    ...optimistic(
      qc,
      ({ id }: { id: number; into: number }) => [
        [
          ['rigs'],
          (old) =>
            patchItems<Rig>(
              old,
              (r) => r.id === id,
              () => null,
            ),
        ],
        [
          ['rig-suggestions'],
          (old) =>
            patchItems<{ rig_id: number; into: number }>(
              old,
              (x) => x.rig_id === id || x.into === id,
              () => null,
            ),
        ],
      ],
      elsewhere,
    ),
    meta: { failed: "Couldn't merge the rigs" },
  })
  const [editing, setEditing] = useState<number | null>(null)
  const [name, setName] = useState('')
  const [mergeInto, setMergeInto] = useState<Record<number, string>>({})
  const list = rigs.data ?? []
  const byId = Object.fromEntries(list.map((r) => [r.id, r]))

  return (
    <SettingsSection id="rigs" title="Rigs" meta={rigs.isSuccess ? list.length : undefined}>
      <p className="muted">
        Detected from TELESCOP, INSTRUME and FOCALLEN. Merge duplicates to share datasets.
      </p>
      {(sugg.data ?? []).map((x) => (
        <div key={`${x.rig_id}-${x.into}`} className={s.suggest}>
          <span>Possible duplicate: {x.why}</span>
          <Button variant="primary" onClick={() => merge.mutate({ id: x.rig_id, into: x.into })}>
            Merge into {byId[x.into]?.name ?? 'it'}
          </Button>
        </div>
      ))}
      <ul className={s.patternList}>
        {list.map((r) => (
          <li key={r.id} className={`${s.patternRow} ${s.rigRow} ${r.id < 0 ? s.saving : ''}`}>
            <div>
              {editing === r.id ? (
                <form
                  className={s.inlineForm}
                  onSubmit={(e) => {
                    e.preventDefault()
                    if (name.trim() && name !== r.name) edit.mutate({ id: r.id, name: name.trim() })
                    setEditing(null)
                  }}
                >
                  <input value={name} onChange={(e) => setName(e.target.value)} aria-label="Rig name" />
                  <Button type="submit">Save</Button>
                </form>
              ) : (
                <strong>{r.name}</strong>
              )}
              <div className="muted">
                {[
                  r.camera,
                  r.telescope,
                  r.focal_mm ? `${r.focal_mm} mm` : '',
                  r.image_scale ? `${r.image_scale.toFixed(2)}″/px` : '',
                ]
                  .filter(Boolean)
                  .join(' · ')}{' '}
                · {r.datasets} dataset{r.datasets === 1 ? '' : 's'} · {r.sessions} session
                {r.sessions === 1 ? '' : 's'}
              </div>
            </div>
            <div className={`${s.rowActions} ${s.rigActions}`}>
              <select
                aria-label={`Calibration for ${r.name}`}
                value={r.calibration}
                disabled={r.id < 0}
                onChange={(e) =>
                  edit.mutate({ id: r.id, calibration: e.target.value as 'masters' | 'flats' | 'none' })
                }
              >
                <option value="masters">Darks and flats</option>
                <option value="flats">Flats and bias, no darks</option>
                <option value="none">None: calibrated in the camera</option>
              </select>
              <select
                aria-label={`Mount for ${r.name}`}
                value={r.mount}
                disabled={r.id < 0}
                onChange={(e) => edit.mutate({ id: r.id, mount: e.target.value as Mount })}
              >
                <option value="">Mount: not said</option>
                <option value="equatorial">Equatorial</option>
                <option value="altaz">Alt-az</option>
                <option value="tracker">Star tracker</option>
                <option value="smart">Smart telescope</option>
              </select>
              <Button
                disabled={r.id < 0}
                onClick={() => {
                  setEditing(r.id)
                  setName(r.name)
                }}
              >
                Rename
              </Button>
              <select
                aria-label={`Merge ${r.name} into`}
                value={mergeInto[r.id] ?? ''}
                onChange={(e) => setMergeInto({ ...mergeInto, [r.id]: e.target.value })}
              >
                <option value="">Merge into…</option>
                {list
                  .filter((o) => o.id !== r.id)
                  .map((o) => (
                    <option key={o.id} value={o.id}>
                      {o.name} ({o.camera})
                    </option>
                  ))}
              </select>
              {mergeInto[r.id] && (
                <Button
                  variant="danger"
                  disabled={Number(mergeInto[r.id]) < 0}
                  onClick={() => merge.mutate({ id: r.id, into: Number(mergeInto[r.id]) })}
                >
                  Merge
                </Button>
              )}
            </div>
          </li>
        ))}
      </ul>
      {draft ? (
        <div className={s.formGrid}>
          {(
            [
              ['name', 'Name', 'Redcat 51 + 2600MC'],
              ['telescope', 'Telescope (as in TELESCOP)', 'Redcat 51'],
              ['camera', 'Camera (as in INSTRUME)', 'ZWO ASI2600MC Pro'],
              ['focal', 'Focal length, mm', '250'],
            ] as const
          ).map(([k, label, ph]) => (
            <label key={k} className={s.inline}>
              {label}
              <input
                value={draft[k]}
                placeholder={ph}
                onChange={(e) => setDraft({ ...draft, [k]: e.target.value })}
              />
            </label>
          ))}
          <div className={s.rowActions}>
            <Button
              variant="primary"
              disabled={!draft.name.trim()}
              onClick={() => {
                // the rig shows at once and the form closes; a failure reopens it as it was
                const was = draft
                add.mutate(
                  {
                    name: draft.name.trim(),
                    telescope: draft.telescope,
                    camera: draft.camera,
                    focal_mm: draft.focal ? Number(draft.focal) : null,
                    mount: draft.mount,
                  },
                  { onError: () => setDraft(was) },
                )
                setDraft(null)
              }}
            >
              Add rig
            </Button>
            <Button onClick={() => setDraft(null)}>Cancel</Button>
          </div>
        </div>
      ) : (
        <Button onClick={() => setDraft({ name: '', telescope: '', camera: '', focal: '', mount: '' })}>
          Add rig…
        </Button>
      )}
    </SettingsSection>
  )
}
