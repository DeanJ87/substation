// Where a library's subs were shot, when their headers don't say (spec 008), plus what the renderer may say about it
// (spec 020): a region name and the Bortle class, never the site's name or position.
import { useState } from 'react'
import { Button } from '../../components/ui'
import { usePatchLibrary, type Lib } from './LibraryAccess'
import s from './settings.module.css'

type Form = { name: string; lat: string; lon: string; region: string; bortle: string }

const summary = (site: Lib['site']) => {
  const parts = [
    site.name,
    site.region && `region ${site.region}`,
    site.bortle != null && `Bortle ${site.bortle}`,
  ].filter(Boolean)
  return parts.length ? parts.join(' · ') : 'No site set'
}

export function LibrarySite({ lib, readOnly }: { lib: Lib; readOnly: boolean }) {
  const patch = usePatchLibrary()
  const [form, setForm] = useState<Form | null>(null)
  const site = lib.site
  if (!form)
    return (
      <div className={s.roleControls}>
        <span>
          Site: <span className="muted">{summary(site)}</span>
        </span>
        {!readOnly && (
          <Button
            aria-label={`Edit the site of ${lib.name}`}
            onClick={() =>
              setForm({
                name: site.name ?? '',
                lat: site.lat?.toString() ?? '',
                lon: site.lon?.toString() ?? '',
                region: site.region ?? '',
                bortle: site.bortle?.toString() ?? '',
              })
            }
          >
            Edit site
          </Button>
        )}
      </div>
    )
  return (
    <form
      className={`${s.formGrid} ${s.roleControls}`}
      aria-label={`Site of ${lib.name}`}
      onSubmit={(e) => {
        e.preventDefault()
        patch.mutate(
          {
            id: lib.id,
            body: {
              site: {
                name: form.name.trim() || null,
                lat: form.lat === '' ? null : Number(form.lat),
                lon: form.lon === '' ? null : Number(form.lon),
                region: form.region.trim(),
                bortle: form.bortle === '' ? null : Number(form.bortle),
              },
            },
          },
          { onSuccess: () => setForm(null) },
        )
      }}
    >
      <label className={s.inline}>
        Site
        <input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
      </label>
      <label className={s.inline}>
        Latitude
        <input
          className={s.num}
          inputMode="decimal"
          value={form.lat}
          onChange={(e) => setForm({ ...form, lat: e.target.value })}
        />
      </label>
      <label className={s.inline}>
        Longitude
        <input
          className={s.num}
          inputMode="decimal"
          value={form.lon}
          onChange={(e) => setForm({ ...form, lon: e.target.value })}
        />
      </label>
      <SiteRenderFields
        region={form.region}
        bortle={form.bortle}
        onChange={(next) => setForm({ ...form, ...next })}
      />
      <span className={s.rowActions}>
        <Button type="submit" variant="primary" disabled={patch.isPending}>
          Save site
        </Button>
        <Button onClick={() => setForm(null)}>Cancel</Button>
      </span>
    </form>
  )
}

/** Spec 020: what the renderer may say about a site. Region is the only place name shared outside SubStation (never
 * the site's name or position); Bortle class describes the sky. */
export function SiteRenderFields({
  region,
  bortle,
  onChange,
  disabled,
}: {
  region: string
  bortle: string
  onChange: (next: { region?: string; bortle?: string }) => void
  disabled?: boolean
}) {
  return (
    <>
      <label
        className={s.inline}
        title="The only place name shared with the renderer, e.g. a county or national park"
      >
        Region
        <input
          value={region}
          maxLength={100}
          placeholder="e.g. a county"
          disabled={disabled}
          onChange={(e) => onChange({ region: e.target.value })}
          aria-label="Region"
        />
      </label>
      <label className={s.inline}>
        Bortle class
        <select
          value={bortle}
          disabled={disabled}
          onChange={(e) => onChange({ bortle: e.target.value })}
          aria-label="Bortle class"
        >
          <option value="">Not set</option>
          {[1, 2, 3, 4, 5, 6, 7, 8, 9].map((n) => (
            <option key={n} value={n}>
              {n}
            </option>
          ))}
        </select>
      </label>
    </>
  )
}
