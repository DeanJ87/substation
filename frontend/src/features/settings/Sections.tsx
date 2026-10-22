// Settings sections from the design (v2 A4, spec 008): Folders, Grading, Stacking, Metadata sources, Workers.
import {
  fileMode,
  localPathMap,
  saveFileMode,
  saveLocalPathMap,
  type FileMode,
  type PathMap,
} from '../../components/FilePath'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useMemo, useState } from 'react'
import { api, unwrap } from '../../api/client'
import { optimistic, patchItems } from '../../api/optimistic'
import type { components } from '../../api/schema'
import { toast } from '../../components/Toasts'
import { Help } from '../../components/Help'
import { Button, FieldGroup, Input, Tag } from '../../components/ui'
import { LoadMore } from '../../components/LoadMore'
import { useProgressive } from '../../components/useProgressive'
import { bytes, countText, dateTimeText } from '../format'
import { tempId } from '../metadata/queries'
import { useDraft, useSaveSettings, useSettings, type Processing } from './draft'
import s from './settings.module.css'
import { SettingsSection } from './SettingsSection'
import { MountMode, RoleControls } from './LibraryAccess'
import { LibrarySite, SiteRenderFields } from './LibrarySite'

const when = (iso: string | null | undefined) => (iso ? dateTimeText(iso) : 'never')

export function Folders() {
  const qc = useQueryClient()
  const libs = useQuery({ queryKey: ['libraries'], queryFn: async () => unwrap(await api.GET('/libraries')) })
  const health = useQuery({ queryKey: ['health'], queryFn: async () => unwrap(await api.GET('/health')) })
  // nothing on the row changes until the scan runs, so say it's been asked for
  const rescan = useMutation({
    mutationFn: async (id: number) =>
      unwrap(await api.POST('/libraries/{id}/rescan', { params: { path: { id } } })),
    onMutate: () => toast('Rescan requested.'),
    onSettled: () => void qc.invalidateQueries({ queryKey: ['libraries'] }),
    meta: { failed: "Couldn't start the rescan" },
  })
  const h = health.data as { disk_free_bytes?: number | null; disk_total_bytes?: number | null } | undefined
  const free = bytes(h?.disk_free_bytes)
  const total = bytes(h?.disk_total_bytes)
  const folders = (libs.data ?? []).filter((l) => l.enabled)
  const { draft, set, readOnly } = useDraft()
  const days = draft?.archive?.suggest_after_days ?? 60
  return (
    <SettingsSection
      id="folders"
      title="Folders"
      meta={libs.isSuccess ? folders.length : undefined}
      help={
        <>
          Mount new folders under /data/library and restart the container. SubStation writes only to a library
          mounted read-write: the bin can delete there, and it can be an active library (new subs and work in
          progress) or an archive (finished collections move there from a collection's page, and can be
          brought back).
        </>
      }
    >
      <ul className={s.patternList}>
        {folders.map((l) => (
          <li key={l.id} className={`${s.patternRow} ${s.libraryRow}`}>
            <div>
              <strong className={s.mono}>{l.mount_path}</strong>
              <div className="muted">
                <span className={`${s.dot} ${l.status === 'ok' ? s.dotOk : s.dotWarn}`} aria-hidden="true" />
                {l.status === 'ok'
                  ? 'Watching'
                  : l.status === 'unreachable'
                    ? 'Unreachable'
                    : l.status} · {countText(l.frame_count)} files · last full scan{' '}
                {when(l.last_full_sweep_at)} · <MountMode lib={l} />
              </div>
              <RoleControls lib={l} all={folders} readOnly={readOnly} />
              <LibrarySite lib={l} readOnly={readOnly} />
            </div>
            <div className={s.rowActions}>
              <Button
                disabled={rescan.isPending && rescan.variables === l.id}
                onClick={() => rescan.mutate(l.id)}
              >
                Rescan
              </Button>
            </div>
          </li>
        ))}
      </ul>
      {draft && (
        <div className={s.inline}>
          <label>
            Suggest archiving a collection after{' '}
            <input
              className={s.num}
              type="number"
              min={0}
              step={1}
              value={days}
              disabled={readOnly}
              aria-label="Suggest archiving after (days without new subs)"
              onChange={(e) =>
                e.target.value !== '' && set('archive', 'suggest_after_days', Number(e.target.value))
              }
            />{' '}
            days without new subs <span className="muted">(and a current master; 0: never)</span>
          </label>
        </div>
      )}
      <p className="muted">
        Output: <span className={s.mono}>/data/substation</span> · {free.value} {free.unit} free of{' '}
        {total.value} {total.unit}
      </p>
    </SettingsSection>
  )
}

const MEASURES: {
  key: 'fwhm' | 'stars' | 'background' | 'eccentricity'
  name: string
  dir: string
  why: string
  rel: boolean
}[] = [
  { key: 'fwhm', name: 'FWHM', dir: 'above', why: 'Soft stars: seeing, focus or dew.', rel: true },
  { key: 'stars', name: 'Star count', dir: 'below', why: 'Fewer stars: cloud, haze or dew.', rel: true },
  {
    key: 'background',
    name: 'Background',
    dir: 'above',
    why: 'Brighter sky: moonlight, twilight or cloud.',
    rel: true,
  },
  {
    key: 'eccentricity',
    name: 'Eccentricity',
    dir: 'above',
    why: 'Elongated stars: tracking, wind or tilt.',
    rel: false,
  },
]

function Num({
  value,
  onChange,
  step = 0.05,
  label,
  disabled,
}: {
  value: number
  onChange: (v: number) => void
  step?: number
  label: string
  disabled: boolean
}) {
  return (
    <input
      className={s.num}
      type="number"
      step={step}
      min={0}
      value={value}
      disabled={disabled}
      aria-label={label}
      onChange={(e) => e.target.value !== '' && onChange(Number(e.target.value))}
    />
  )
}

export function Grading() {
  const { draft, set, readOnly } = useDraft()
  if (!draft) return null
  const g = draft.grading
  return (
    <SettingsSection id="grading" title="Grading">
      <p className="muted">Relative to the session median.</p>
      <table className={s.table}>
        <thead>
          <tr>
            <th>Measure</th>
            <th>Down-weight</th>
            <th>Reject</th>
            <th>Cause</th>
          </tr>
        </thead>
        <tbody>
          {MEASURES.map((m) => (
            <tr key={m.key}>
              <td>
                <strong>{m.name}</strong>
                <div className="muted">{m.rel ? `× the session median, ${m.dir}` : `absolute, ${m.dir}`}</div>
              </td>
              {[0, 1].map((i) => (
                <td key={i}>
                  <Num
                    label={`${m.name} ${i ? 'reject' : 'down-weight'} level`}
                    value={g[m.key][i]}
                    disabled={readOnly}
                    onChange={(v) => {
                      const next = [...g[m.key]] as [number, number]
                      next[i] = v
                      set('grading', m.key, next)
                    }}
                  />
                  {m.rel ? '×' : ''}
                </td>
              ))}
              <td className="muted">{m.why}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <div className={s.inline}>
        Minimum subs for a final grade
        <Num
          label="Fewest subs"
          step={1}
          value={g.min_session}
          disabled={readOnly}
          onChange={(v) => set('grading', 'min_session', Math.round(v))}
        />
      </div>
      <p className="muted">Smaller sessions get provisional grades.</p>
      <label className={s.inline}>
        <input
          type="checkbox"
          disabled={readOnly}
          checked={g.use_conditions !== false}
          onChange={(e) => set('grading', 'use_conditions', e.target.checked)}
        />
        Use SQM and cloud when recorded
      </label>
      <p className="muted">SQM or cloud alone flags, never rejects.</p>
    </SettingsSection>
  )
}

function Choice<K extends keyof Processing>({
  section,
  field,
  label,
  options,
}: {
  section: K
  field: string
  label: string
  options: [string, string][]
}) {
  const { draft, set, readOnly } = useDraft()
  if (!draft) return null
  const value = (draft[section] as Record<string, unknown>)[field] as string
  return (
    <label className={s.inline}>
      {label}
      <select value={value} disabled={readOnly} onChange={(e) => set(section, field, e.target.value)}>
        {options.map(([v, t]) => (
          <option key={v} value={v}>
            {t}
          </option>
        ))}
      </select>
    </label>
  )
}

export function Stacking() {
  const { draft, set, readOnly } = useDraft()
  if (!draft) return null
  const st = draft.stacking
  return (
    <SettingsSection id="stacking" title="Stacking">
      <p className="muted">Defaults for new masters.</p>
      <div className={s.formGrid}>
        <Choice
          section="stacking"
          field="rejection"
          label="Rejection"
          options={[
            ['winsorized', 'Winsorised sigma clipping'],
            ['sigma', 'Sigma clipping'],
            ['linear', 'Linear fit clipping'],
          ]}
        />
        <div className={s.inline}>
          Sigma low / high
          {[0, 1].map((i) => (
            <Num
              key={i}
              label={`Sigma ${i ? 'high' : 'low'}`}
              step={0.1}
              value={st.sigma[i]}
              disabled={readOnly}
              onChange={(v) => {
                const next = [...st.sigma] as [number, number]
                next[i] = v
                set('stacking', 'sigma', next)
              }}
            />
          ))}
        </div>
        <Choice
          section="stacking"
          field="weighting"
          label="Weighting"
          options={[
            ['grade', 'Grade'],
            ['snr', 'SNR'],
            ['equal', 'Equal'],
          ]}
        />
        <Choice
          section="stacking"
          field="reference"
          label="Registration reference"
          options={[
            ['best_fwhm', 'Best FWHM'],
            ['most_stars', 'Most stars'],
            ['manual', 'Manual'],
          ]}
        />
        <Choice
          section="stacking"
          field="auto"
          label="Auto-stack"
          options={[
            ['never', 'Never'],
            ['session', 'After each session'],
            ['every_n', 'Every N new subs'],
          ]}
        />
        {st.auto === 'session' && (
          <div className={s.inline}>
            Stack after no new subs for (hours)
            <Num
              value={st.auto_quiet_hours ?? 3}
              step={0.5}
              label="Quiet time after a session, hours"
              disabled={readOnly}
              onChange={(n) => set('stacking', 'auto_quiet_hours', n)}
            />
          </div>
        )}
        {st.auto === 'every_n' && (
          <div className={s.inline}>
            New usable subs per master
            <Num
              value={st.auto_every_n ?? 30}
              step={1}
              label="New usable subs per automatic master"
              disabled={readOnly}
              onChange={(n) => set('stacking', 'auto_every_n', Math.round(n))}
            />
          </div>
        )}
        <Choice section="stacking" field="format" label="Output" options={[['fits', 'FITS, 32-bit float']]} />
      </div>
    </SettingsSection>
  )
}

// spec 010: what each step does, its tool, and its parameters with their ranges
const POST_STEPS: Record<
  string,
  { label: string; tool: string; params: [string, string, number, number][] }
> = {
  background: {
    label: 'Background extraction',
    tool: 'GraXpert',
    params: [['smoothing', 'Smoothing', 0, 1]],
  },
  deconvolve: {
    label: 'Deconvolution',
    tool: 'BlurXTerminator',
    params: [
      ['sharpen_stars', 'Star sharpening', 0, 0.7],
      ['adjust_halos', 'Star halos', -0.5, 0.5],
      ['sharpen_nonstellar', 'Non-stellar sharpening', 0, 1],
    ],
  },
  denoise: {
    label: 'Noise reduction',
    tool: 'NoiseXTerminator, else GraXpert',
    params: [['amount', 'Amount (GraXpert)', 0, 1]],
  },
  starless: { label: 'Starless and stars-only', tool: 'StarXTerminator', params: [] },
}

/** Owner 2026-10-12: files are opened where they are, not downloaded. Map the server's paths to how people's machines
 * see the same share; a browser can keep its own mapping (a Mac at /Volumes/Photography, a PC at Z:\Photography). */
export function FilePaths() {
  const { draft, set, readOnly } = useDraft()
  const [mine, setMine] = useState(() => localPathMap())
  const [mode, setMode] = useState<FileMode>(fileMode)
  if (!draft) return null
  const site = draft.paths?.map ?? []
  const row = (list: PathMap[], i: number, change: (next: PathMap[]) => void, disabled: boolean) => (
    <div key={i} className={s.inline}>
      <Input
        aria-label="Server path"
        placeholder="/data/library/organised"
        value={list[i].from}
        disabled={disabled}
        onChange={(e) => change(list.map((m, j) => (j === i ? { ...m, from: e.target.value } : m)))}
      />
      →
      <Input
        aria-label="Shown as"
        placeholder="Z:\\Photography\\Deep Sky\\Organised"
        value={list[i].to}
        disabled={disabled}
        onChange={(e) => change(list.map((m, j) => (j === i ? { ...m, to: e.target.value } : m)))}
      />
      <Button
        size="sm"
        variant="ghost"
        disabled={disabled}
        onClick={() => change(list.filter((_, j) => j !== i))}
      >
        Remove
      </Button>
    </div>
  )
  return (
    <SettingsSection
      id="paths"
      title="File paths"
      help={
        <>
          Masters and processed versions can open where they are on your share, or download. Map the server's
          folders to the drive or share your machines use; a file no mapping reaches downloads instead.
        </>
      }
    >
      <FieldGroup legend="In this browser, files">
        <div className={s.inline}>
          {(
            [
              ['open', 'Open where they are'],
              ['download', 'Download'],
            ] as const
          ).map(([value, label]) => (
            <label key={value} className={s.radio}>
              <input
                type="radio"
                name="file-mode"
                checked={mode === value}
                onChange={() => {
                  setMode(value)
                  saveFileMode(value)
                }}
              />
              {label}
            </label>
          ))}
        </div>
      </FieldGroup>
      <FieldGroup legend="Mappings for everyone">
        {site.map((_, i) => row(site, i, (next) => set('paths', 'map', next), readOnly))}
        <div>
          <Button
            size="sm"
            disabled={readOnly}
            onClick={() => set('paths', 'map', [...site, { from: '', to: '' }])}
          >
            Add a mapping
          </Button>
        </div>
      </FieldGroup>
      <FieldGroup legend="Mappings for this browser only">
        {mine.map((_, i) =>
          row(
            mine,
            i,
            (next) => {
              setMine(next)
              saveLocalPathMap(next)
            },
            false,
          ),
        )}
        <div>
          <Button
            size="sm"
            onClick={() => {
              const next = [...mine, { from: '', to: '' }]
              setMine(next)
            }}
          >
            Add a mapping
          </Button>
        </div>
      </FieldGroup>
    </SettingsSection>
  )
}

/** Spec 010 (owner 2026-10-12): what the finisher can run, and RC-Astro activation from the web — paste the
 * code from rc-astro.com → Account (it expires in 30 minutes); the finisher runs the activation itself. */
function FinishingTools() {
  const q = useQuery({
    queryKey: ['post-tools'],
    queryFn: async () => unwrap(await api.GET('/post/tools')),
    refetchInterval: (query) => (query.state.data?.checking ? 3000 : false),
  })
  const d = q.data
  const tool = (name: string, t: { ready?: boolean; reason?: string } | undefined) => (
    <Tag tone={t?.ready ? 'ok' : 'neutral'} title={t?.reason || undefined}>
      {name}: {t?.ready ? 'ready' : d?.checked_at ? 'not ready' : 'not checked yet'}
    </Tag>
  )
  return (
    <div className={s.toolStatus}>
      {tool('GraXpert', d?.graxpert as { ready?: boolean; reason?: string })}
      {tool('RC-Astro', d?.rc_astro as { ready?: boolean; reason?: string })}
      <span className="muted">
        {d?.checking
          ? 'Asking the finisher…'
          : d?.checked_at
            ? `Checked ${dateTimeText(d.checked_at)} on ${d.host}${d.note ? ` · ${d.note}` : ''}`
            : ''}
      </span>
      <Help topic="Where the tools run">
        These tools run on a post-processing helper on a faster machine, reported each time it asks for work.
        RC-Astro is activated on that machine itself.
      </Help>
    </div>
  )
}

export function PostProcessing() {
  const { draft, set, readOnly } = useDraft()
  if (!draft?.post) return null
  const p = draft.post
  const setStep = (i: number, key: string, v: unknown) =>
    set(
      'post',
      'steps',
      p.steps.map((st, j) => (j === i ? { ...st, [key]: v } : st)),
    )
  return (
    <SettingsSection
      id="post"
      title="Master post-processing"
      help={
        <>
          After a master integrates, run it through these tools in order. The master itself is never changed:
          each step keeps its own linear 32-bit copy. Tools run on the worker and must be installed there;
          RC-Astro's need your own licence. A missing tool is skipped, never a failed master.
        </>
      }
    >
      <FinishingTools />
      <label className={s.inline}>
        <input
          type="checkbox"
          checked={p.enabled}
          disabled={readOnly}
          onChange={(e) => set('post', 'enabled', e.target.checked)}
        />
        Post-process new masters
      </label>
      <label className={s.inline}>
        <input
          type="checkbox"
          checked={p.gpu}
          disabled={readOnly}
          onChange={(e) => set('post', 'gpu', e.target.checked)}
        />
        Use the GPU when the worker has one
      </label>
      {/* one row per step (B05): checkbox and name, the tool, then its settings */}
      <ol className={s.steps}>
        {p.steps.map((st, i) => {
          const meta = POST_STEPS[st.step] ?? { label: st.step, tool: '', params: [] }
          return (
            <li key={st.step} className={s.step}>
              <label className={s.stepName}>
                <input
                  type="checkbox"
                  checked={!!st.enabled}
                  disabled={readOnly || !p.enabled}
                  onChange={(e) => setStep(i, 'enabled', e.target.checked)}
                />
                <strong>{meta.label}</strong>
              </label>
              <span className="muted">{meta.tool}</span>
              <span className={s.stepParams}>
                {st.enabled &&
                  meta.params.map(([key, label, min, max]) => (
                    <span key={key} className={s.inline} title={`${min} to ${max}`}>
                      {label}
                      <Num
                        label={`${meta.label}: ${label}, ${min} to ${max}`}
                        step={0.05}
                        value={Number(st[key] ?? 0)}
                        disabled={readOnly || !p.enabled}
                        onChange={(v) => setStep(i, key, Math.min(max, Math.max(min, v)))}
                      />
                    </span>
                  ))}
              </span>
            </li>
          )
        })}
      </ol>
    </SettingsSection>
  )
}

export function MetadataSources() {
  const q = useSettings()
  const [site, setSite] = useState<{
    name: string
    lat: string
    lon: string
    region: string
    bortle: string
  } | null>(null)
  const save = useSaveSettings("Couldn't save the site")
  const d = q.data
  if (!d) return null
  const cur = site ?? {
    name: d.site_name ?? '',
    lat: d.site_lat?.toString() ?? '',
    lon: d.site_lon?.toString() ?? '',
    region: d.site_region ?? '',
    bortle: d.site_bortle?.toString() ?? '',
  }
  const aliases = Object.entries(d.filter_aliases ?? {})
  return (
    <SettingsSection
      id="sources"
      title="Metadata sources"
      help={
        <>
          Order: headers, path patterns, then these defaults. Site sets night boundaries when a sub has no
          position. Region and Bortle class are what the renderer may show about where you shot: never the
          site's name or position.
        </>
      }
    >
      <form
        className={s.formGrid}
        onSubmit={(e) => {
          e.preventDefault()
          // the saved site shows at once; a failure brings the typed values back
          const was = site
          save.mutate(
            {
              site_name: cur.name || null,
              site_lat: cur.lat === '' ? null : Number(cur.lat),
              site_lon: cur.lon === '' ? null : Number(cur.lon),
              site_region: cur.region.trim(),
              site_bortle: cur.bortle === '' ? null : Number(cur.bortle),
            },
            { onError: () => setSite(was) },
          )
          setSite(null)
        }}
      >
        <label className={s.inline}>
          Site
          <input
            value={cur.name}
            onChange={(e) => setSite({ ...cur, name: e.target.value })}
            aria-label="Site name"
          />
        </label>
        <label className={s.inline}>
          Latitude
          <input
            className={s.num}
            value={cur.lat}
            onChange={(e) => setSite({ ...cur, lat: e.target.value })}
            aria-label="Latitude"
          />
        </label>
        <label className={s.inline}>
          Longitude
          <input
            className={s.num}
            value={cur.lon}
            onChange={(e) => setSite({ ...cur, lon: e.target.value })}
            aria-label="Longitude"
          />
        </label>
        <SiteRenderFields
          region={cur.region}
          bortle={cur.bortle}
          onChange={(next) => setSite({ ...cur, ...next })}
        />
        {site && (
          <Button type="submit" variant="primary">
            Save site
          </Button>
        )}
      </form>
      <div>
        <strong>Filter aliases</strong>
        <div className="muted">
          {aliases.length ? aliases.map(([k, v]) => `${k} → ${v}`).join(' · ') : 'None'}
        </div>
      </div>
      <SourcesInUse />
    </SettingsSection>
  )
}

/** Workers (005 T001/T002): how many worker processes run and how many may stack at once. Both apply live: the
 * supervisor scales workers within a minute and each worker reads the stacking slots at its next job. */
export function Workers() {
  const q = useSettings()
  const d = q.data
  const [count, setCount] = useState<number | null>(null)
  const [heavy, setHeavy] = useState<number | null>(null)
  const [budget, setBudget] = useState<number | null>(null)
  const [threads, setThreads] = useState<string | null>(null)
  const [mem, setMem] = useState<string | null>(null)
  // while a stack or master build runs (005-DR-16): blank means every core and 80%
  const [stackThreads, setStackThreads] = useState<string | null>(null)
  const [stackMem, setStackMem] = useState<string | null>(null)
  const save = useSaveSettings("Couldn't apply the worker settings")
  const reset = () => {
    setCount(null)
    setHeavy(null)
    setBudget(null)
    setThreads(null)
    setMem(null)
    setStackThreads(null)
    setStackMem(null)
  }
  // the new values become the shown ones at once; a failure brings the edits back
  const apply = () => {
    const was = { count, heavy, budget, threads, mem, stackThreads, stackMem }
    save.mutate(
      {
        ...(count != null ? { worker_count: count } : {}),
        ...(heavy != null ? { siril_heavy_slots: heavy } : {}),
        ...(budget != null ? { work_budget_gb: budget } : {}),
        ...(threads != null ? { siril_threads: threads ? Number(threads) : null } : {}),
        ...(mem != null ? { siril_mem_ratio: mem ? Number(mem) / 100 : null } : {}),
        ...(stackThreads != null ? { stack_threads: stackThreads ? Number(stackThreads) : null } : {}),
        ...(stackMem != null ? { stack_mem_ratio: stackMem ? Number(stackMem) / 100 : null } : {}),
      },
      {
        onError: () => {
          setCount(was.count)
          setHeavy(was.heavy)
          setBudget(was.budget)
          setThreads(was.threads)
          setMem(was.mem)
          setStackThreads(was.stackThreads)
          setStackMem(was.stackMem)
        },
      },
    )
    reset()
  }
  if (!d) return null
  const readOnly = !d.can_edit
  const workers = count ?? d.worker_count ?? d.workers_alive
  const slots = heavy ?? d.siril_heavy_slots
  const dirty =
    count != null ||
    heavy != null ||
    budget != null ||
    threads != null ||
    mem != null ||
    stackThreads != null ||
    stackMem != null
  return (
    <SettingsSection
      id="workers"
      title="Workers"
      help={
        <>
          {d.workers_alive} worker{d.workers_alive === 1 ? '' : 's'} on {d.cpu_threads} CPU threads.
        </>
      }
    >
      <div className={s.formGrid}>
        <label className={s.inline}>
          Workers
          <input
            type="number"
            min={1}
            max={16}
            value={workers}
            disabled={readOnly}
            onChange={(e) => setCount(Number(e.target.value))}
          />
        </label>
        <label className={s.inline}>
          Stacking slots
          <input
            type="number"
            min={1}
            max={Math.min(4, workers)}
            value={slots}
            disabled={readOnly}
            onChange={(e) => setHeavy(Number(e.target.value))}
          />
        </label>
        <label className={s.inline}>
          Stacking work budget (GB)
          <input
            type="number"
            min={5}
            step={10}
            value={budget ?? d.work_budget_gb}
            disabled={readOnly}
            onChange={(e) => setBudget(Number(e.target.value))}
          />
        </label>
        <label className={s.inline}>
          Siril threads each
          <input
            type="number"
            min={1}
            max={d.cpu_threads}
            placeholder="auto"
            value={threads ?? d.siril_threads ?? ''}
            disabled={readOnly}
            onChange={(e) => setThreads(e.target.value)}
          />
        </label>
        <label className={s.inline}>
          Siril memory each (% of free)
          <input
            type="number"
            min={5}
            max={90}
            placeholder={
              d.siril_mem_effective != null ? `auto: ${Math.round(d.siril_mem_effective * 100)}` : 'auto'
            }
            value={mem ?? (d.siril_mem_ratio != null ? Math.round(d.siril_mem_ratio * 100) : '')}
            disabled={readOnly}
            onChange={(e) => setMem(e.target.value)}
          />
        </label>
        <label className={s.inline}>
          Threads while stacking
          <input
            type="number"
            min={1}
            placeholder={`all: ${d.cores}`}
            value={stackThreads ?? d.stack_threads ?? ''}
            disabled={readOnly}
            onChange={(e) => setStackThreads(e.target.value)}
          />
        </label>
        <label className={s.inline}>
          Memory while stacking (% of free)
          <input
            type="number"
            min={10}
            max={95}
            placeholder="auto: 80"
            value={stackMem ?? (d.stack_mem_ratio != null ? Math.round(d.stack_mem_ratio * 100) : '')}
            disabled={readOnly}
            onChange={(e) => setStackMem(e.target.value)}
          />
        </label>
      </div>
      <div className={s.formGrid}>
        <Choice
          section="queue"
          field="priority_mode"
          label="Work order"
          options={[
            ['new_first', 'New subs first'],
            ['in_order', 'Oldest first'],
          ]}
        />
      </div>
      <p className="muted">
        Changes apply without a restart.{' '}
        <Help topic="Sizing workers">
          A stack can use several GB of memory; with 8 GB for Docker, use one stacking slot. A stack needs
          about twice its subs' size in work budget.
        </Help>
      </p>
      <div className={s.rowActions}>
        <Button disabled={readOnly || !dirty} onClick={apply}>
          {save.isPending && !dirty ? 'Applying…' : 'Apply'}
        </Button>
        {dirty && <Button onClick={reset}>Discard</Button>}
      </div>
    </SettingsSection>
  )
}

const ROLE_TEXT: Record<string, string> = {
  admin: 'Admin',
  standard: 'Standard',
  viewer: "Read-only: can review, can't override",
}

/** Users (008-DR-07): accounts with role and last sign-in; admins add users and change roles. */
export function Users() {
  const qc = useQueryClient()
  const { readOnly } = useDraft()
  const [userSort, setUserSort] = useState<'name' | 'role' | 'last'>('name')
  const q = useQuery({
    queryKey: ['users'],
    enabled: !readOnly,
    queryFn: async () => unwrap(await api.GET('/users')),
  })
  type User = components['schemas']['UserOut']
  type Role = 'admin' | 'standard' | 'viewer'
  // role changes run in order, so the last one picked is the one that sticks
  const role = useMutation({
    scope: { id: 'user-roles' },
    mutationFn: async ({ id, r }: { id: number; r: Role }) =>
      unwrap(await api.PATCH('/users/{id}', { params: { path: { id } }, body: { role: r } })),
    ...optimistic(qc, ({ id, r }: { id: number; r: Role }) => [
      [
        ['users'],
        (old) =>
          patchItems<User>(
            old,
            (u) => u.id === id,
            (u) => ({ ...u, role: r }),
          ),
      ],
    ]),
    meta: { failed: "Couldn't change the role" },
  })
  const [adding, setAdding] = useState<{
    username: string
    password: string
    role: 'admin' | 'standard' | 'viewer'
  } | null>(null)
  const add = useMutation({
    mutationFn: async (body: { username: string; password: string; role: Role }) =>
      unwrap(await api.POST('/users', { body })),
    ...optimistic(qc, (body: { username: string; role: Role }) => [
      [
        ['users'],
        (old) =>
          old && [
            ...(old as User[]),
            {
              id: tempId(),
              username: body.username,
              role: body.role,
              last_login: null,
              date_joined: new Date().toISOString(),
            },
          ],
      ],
    ]),
    meta: { failed: "Couldn't add the user" },
  })
  // sorted first, then shown a slice at a time inside the section's own scroll
  const sorted = useMemo(
    () =>
      [...(q.data ?? [])].sort((a, b) =>
        userSort === 'role'
          ? a.role.localeCompare(b.role) || a.username.localeCompare(b.username)
          : userSort === 'last'
            ? (b.last_login ?? '').localeCompare(a.last_login ?? '')
            : a.username.localeCompare(b.username),
      ),
    [q.data, userSort],
  )
  const users = useProgressive(sorted, 60, userSort)
  return (
    <SettingsSection id="users" title="Users" meta={q.isSuccess ? q.data.length : undefined}>
      {readOnly ? (
        <p className="muted">Admins only.</p>
      ) : (
        <>
          <div className={s.rowActions} role="group" aria-label="Sort users">
            <span className="muted">Sort</span>
            {(
              [
                ['name', 'Name'],
                ['role', 'Role'],
                ['last', 'Last sign-in'],
              ] as const
            ).map(([k, label]) => (
              <button
                key={k}
                type="button"
                className={s.sortPill}
                aria-pressed={userSort === k}
                onClick={() => setUserSort(k)}
              >
                {label}
              </button>
            ))}
          </div>
          <div className={s.scrollPane}>
            <ul className={s.patternList}>
              {users.visible.map((u) => (
                <li key={u.id} className={`${s.patternRow} ${u.id < 0 ? s.saving : ''}`}>
                  <div>
                    <strong>{u.username}</strong>
                    <div className="muted">
                      {u.id < 0
                        ? 'saving…'
                        : u.last_login
                          ? `last signed in ${when(u.last_login)}`
                          : 'never signed in'}
                    </div>
                  </div>
                  <select
                    aria-label={`Role for ${u.username}`}
                    value={u.role}
                    disabled={u.id < 0}
                    onChange={(e) => role.mutate({ id: u.id, r: e.target.value as Role })}
                  >
                    {Object.entries(ROLE_TEXT).map(([k, t]) => (
                      <option key={k} value={k}>
                        {t}
                      </option>
                    ))}
                  </select>
                </li>
              ))}
            </ul>
            <LoadMore hasMore={users.hasMore} loading={false} onMore={users.more} />
          </div>
          {adding ? (
            <form
              className={s.formGrid}
              onSubmit={(e) => {
                e.preventDefault()
                // the user shows at once and the form closes; a failure reopens it as it was
                const was = adding
                add.mutate(adding, { onError: () => setAdding(was) })
                setAdding(null)
              }}
            >
              <label className={s.inline}>
                Username
                <input
                  value={adding.username}
                  onChange={(e) => setAdding({ ...adding, username: e.target.value })}
                />
              </label>
              <label className={s.inline}>
                Password
                <input
                  type="password"
                  autoComplete="new-password"
                  value={adding.password}
                  onChange={(e) => setAdding({ ...adding, password: e.target.value })}
                />
              </label>
              <label className={s.inline}>
                Role
                <select
                  value={adding.role}
                  onChange={(e) => setAdding({ ...adding, role: e.target.value as 'admin' })}
                >
                  {Object.entries(ROLE_TEXT).map(([k, t]) => (
                    <option key={k} value={k}>
                      {t}
                    </option>
                  ))}
                </select>
              </label>
              <Button type="submit" variant="primary" disabled={!adding.username.trim() || !adding.password}>
                Add user
              </Button>
              <Button onClick={() => setAdding(null)}>Cancel</Button>
            </form>
          ) : (
            <div>
              <Button onClick={() => setAdding({ username: '', password: '', role: 'standard' })}>
                Add user
              </Button>
            </div>
          )}
        </>
      )}
    </SettingsSection>
  )
}

/** Somewhere to send to: ntfy, a webhook, or Pushover with both its keys. Events and a test need one. */
export function hasDestination(n: {
  ntfy: string
  webhook: string
  pushover_user?: string | null
  pushover_token?: string | null
}): boolean {
  return !!(n.ntfy.trim() || n.webhook.trim() || (n.pushover_user && n.pushover_token))
}

const EVENTS: [string, string][] = [
  ['master_finished', 'Master finished'],
  ['job_failed', 'Job failed'],
  ['awaiting_calibration', 'Awaiting calibration'],
  ['session_summary', 'Session summary'],
]

/** Notifications (008-DR-06, 008-DR-13): ntfy, a webhook or Pushover, which events, and a test send. */
export function Notifications() {
  const { draft, set, readOnly, changes } = useDraft()
  const test = useMutation({
    mutationFn: async () => unwrap(await api.POST('/settings/notifications/test')),
    meta: { failed: "Couldn't send the test" },
  })
  if (!draft) return null
  const n = draft.notifications
  const unsaved = changes.some((c) => c.path[0] === 'notifications')
  return (
    <SettingsSection id="notifications" title="Notifications">
      <p className="muted">Only for things that need you.</p>
      <div className={s.formGrid}>
        <label className={s.inline}>
          ntfy topic
          <input
            value={n.ntfy}
            disabled={readOnly}
            placeholder="https://ntfy.sh/your-topic"
            onChange={(e) => set('notifications', 'ntfy', e.target.value)}
          />
        </label>
        <label className={s.inline}>
          Webhook
          <input
            value={n.webhook}
            disabled={readOnly}
            placeholder="https://example.org/hook"
            onChange={(e) => set('notifications', 'webhook', e.target.value)}
          />
        </label>
        <label className={s.inline}>
          Pushover user key
          <input
            value={n.pushover_user ?? ''}
            disabled={readOnly}
            placeholder="your user or group key"
            autoComplete="off"
            onChange={(e) => set('notifications', 'pushover_user', e.target.value.trim())}
          />
        </label>
        <label className={s.inline}>
          Pushover API token
          <input
            type="password"
            value={n.pushover_token ?? ''}
            disabled={readOnly}
            placeholder="the application's token"
            autoComplete="off"
            onChange={(e) => set('notifications', 'pushover_token', e.target.value.trim())}
          />
        </label>
      </div>
      <div className={s.formGrid}>
        {EVENTS.map(([k, label]) => (
          <label key={k} className={s.inline}>
            <input
              type="checkbox"
              disabled={readOnly}
              checked={n.events.includes(k)}
              onChange={(e) =>
                set(
                  'notifications',
                  'events',
                  e.target.checked ? [...n.events, k] : n.events.filter((x) => x !== k),
                )
              }
            />
            {label}
          </label>
        ))}
      </div>
      <div className={s.rowActions}>
        <Button
          disabled={readOnly || unsaved || test.isPending || !hasDestination(n)}
          title={hasDestination(n) ? undefined : 'Set ntfy, a webhook or Pushover first'}
          onClick={() => test.mutate()}
        >
          {test.isPending ? 'Sending…' : 'Send test'}
        </Button>
        {unsaved && <span className="muted">Save before testing.</span>}
        {test.data && !test.isPending && (
          <span className={test.data.sent ? 'muted' : s.error}>
            {test.data.sent ? 'Sent.' : test.data.failed.join(' · ')}
          </span>
        )}
      </div>
    </SettingsSection>
  )
}

/** Calibration matching (002 FR-010, C17): how far a dark's temperature may differ, and whether a light with no
 * earlier flat may use the next flat taken later. Saving re-checks every light's match. */
export function CalibrationMatching() {
  const { draft, set, readOnly } = useDraft()
  if (!draft) return null
  const c = draft.calibration
  return (
    <SettingsSection
      id="calibration"
      title="Calibration matching"
      help={
        <>
          Darks: exposure, gain, offset, binning, size, temperature. Flats: filter, camera, telescope,
          binning, size; latest on or before the session.
        </>
      }
    >
      <div className={s.inline}>
        Dark temperature within
        <Num
          label="Dark temperature tolerance"
          step={0.5}
          value={c.temp_tolerance_c}
          disabled={readOnly}
          onChange={(v) => set('calibration', 'temp_tolerance_c', v)}
        />
        °C of the light
      </div>
      <label className={s.inline}>
        <input
          type="checkbox"
          disabled={readOnly}
          checked={c.later_flat_fallback}
          onChange={(e) => set('calibration', 'later_flat_fallback', e.target.checked)}
        />
        Use a later flat when none is earlier
      </label>
      <p className="muted">Only if the optical train hasn't moved.</p>
    </SettingsSection>
  )
}

/** Plate solving (spec 009): Siril against its local star catalogues, offline. */
export function PlateSolving() {
  const qc = useQueryClient()
  const { readOnly } = useDraft()
  const q = useQuery({ queryKey: ['solving'], queryFn: async () => unwrap(await api.GET('/solving')) })
  type Solving = components['schemas']['SolvingOut']
  // the remaining subs move to queued at once
  const backfill = useMutation({
    mutationFn: async () => unwrap(await api.POST('/solving/backfill')),
    ...optimistic(qc, () => [
      [
        ['solving'],
        (old) => {
          const o = old as Solving | undefined
          return o && { ...o, queued: o.queued + o.waiting, waiting: 0 }
        },
      ],
    ]),
    meta: { failed: "Couldn't queue the solves" },
  })
  const d = q.data
  return (
    <SettingsSection id="solving" title="Plate solving">
      {!d ? null : d.available ? (
        <>
          <p className="muted">Offline, using Siril's local catalogues.</p>
          <p>
            <span className={s.mono}>{countText(d.solved)}</span> solved ·{' '}
            <span className={s.mono}>{countText(d.failed)}</span> failed ·{' '}
            <span className={s.mono}>{countText(d.waiting)}</span> not tried
          </p>
          <div className={s.rowActions}>
            <Button disabled={readOnly || !d.waiting} onClick={() => backfill.mutate()}>
              Solve {countText(d.waiting)} remaining
            </Button>
            {(backfill.isPending || backfill.data) && <span className="muted">Queued.</span>}
          </div>
        </>
      ) : (
        <p className="muted">
          Off: star catalogues not installed. Add namedstars.dat, unnamedstars.dat, deepstars.dat and
          USNO-NOMAD-1e8.dat (free-astro.org/download/kstars-siril-catalogues) to{' '}
          <span className={s.mono}>{d.catalogue_dir}</span> in the worker.
        </p>
      )}
    </SettingsSection>
  )
}

/** Where each value comes from (008-DR-01): header keyword, path pattern or you, and how many files each decided. */
function SourcesInUse() {
  const q = useQuery({
    queryKey: ['settings-sources'],
    queryFn: async () => unwrap(await api.GET('/settings/sources')),
  })
  const rows = q.data ?? []
  if (!rows.length) return null
  const by = new Map<string, typeof rows>()
  for (const r of rows) by.set(r.field, [...(by.get(r.field) ?? []), r])
  const SOURCE: Record<string, string> = {
    header: 'header',
    pattern: 'path pattern',
    user: 'you',
    master: 'master',
  }
  return (
    <div>
      <strong>Sources in use</strong>
      <table className={s.sourceTable}>
        <tbody>
          {[...by.entries()].map(([field, rs]) => (
            <tr key={field}>
              <th scope="row">{field.replace('_', ' ')}</th>
              {/* one figure per kind of source, "FILTER (header) ×206 · inferred ×43"; every detail on hover (C14) */}
              <td
                title={rs
                  .map((r) => `${r.detail || SOURCE[r.source] || r.source} · ${countText(r.frames)}`)
                  .join('\n')}
              >
                {sourceKinds(rs, SOURCE).join(' · ')}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

/** Sources of one field folded by kind: header keywords by name, everything else as its kind with a total. */
function sourceKinds(
  rs: { source: string; detail?: string | null; frames: number }[],
  names: Record<string, string>,
): string[] {
  const out = new Map<string, number>()
  for (const r of rs) {
    const header = r.source === 'header' && r.detail
    const inferred = !header && /\(inferred\)|inferred/.test(r.detail ?? '')
    const key = header ? `${r.detail} (header)` : inferred ? 'inferred' : (names[r.source] ?? r.source)
    out.set(key, (out.get(key) ?? 0) + r.frames)
  }
  return [...out.entries()].sort((a, b) => b[1] - a[1]).map(([k, n]) => `${k} ×${countText(n)}`)
}
