// A close look at one sub (owner 2026-10-10): the whole sub to zoom (wheel, pinch, + −, fit, 100%) and pan around, and an
// aberration inspector (nine full-resolution crops: corners, edges and centre) to see whether stars are really
// elongated, and where. Made by a worker on request, in a few seconds; Esc closes.
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { type ReactNode, useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { api, unwrap } from '../api/client'
import { optimistic } from '../api/optimistic'
import { Spinner } from './ui'
import { AnnotateToggle, AnnotationOverlay, type AnnotateTarget, useAnnotateSwitch } from './Annotations'
import s from './CloseLook.module.css'
import { anchoredScroll, clampZoom, fitScale as fitOf } from './zoom'
import type { components } from '../api/schema'
import { integrationText, numText, plural } from '../features/format'
import { filterName } from './filters'

export type LookMode = 'full' | 'inspector'
/** What to look at: a sub, a master, or a palette made from a project's combined masters. */
export type LookTarget =
  | { kind: 'sub'; sha: string }
  | { kind: 'master'; id: number }
  | { kind: 'combined'; id: number }
  | { kind: 'palette'; collection: number; project: number | null; name: 'hoo' | 'sho' }

type Integration = components['schemas']['IntegrationOut']
type Look = {
  ready: boolean
  generating?: boolean
  failed?: boolean
  full?: string | null
  inspector?: string | null
  note?: string
  integration?: Integration | null
}

async function status(t: LookTarget): Promise<Look> {
  if (t.kind === 'sub')
    return unwrap(await api.GET('/frames/{sha256}/view', { params: { path: { sha256: t.sha } } }))
  if (t.kind === 'master')
    return unwrap(await api.GET('/stacks/{id}/view', { params: { path: { id: t.id } } }))
  if (t.kind === 'combined')
    return unwrap(await api.GET('/combined/{id}/view', { params: { path: { id: t.id } } }))
  return unwrap(
    await api.GET('/collections/{id}/palette/{name}', {
      params: { path: { id: t.collection, name: t.name }, query: t.project ? { project: t.project } : {} },
    }),
  )
}

async function generate(t: LookTarget): Promise<Look> {
  if (t.kind === 'sub')
    return unwrap(await api.POST('/frames/{sha256}/view', { params: { path: { sha256: t.sha } } }))
  if (t.kind === 'master')
    return unwrap(await api.POST('/stacks/{id}/view', { params: { path: { id: t.id } } }))
  if (t.kind === 'combined')
    return unwrap(await api.POST('/combined/{id}/view', { params: { path: { id: t.id } } }))
  return unwrap(
    await api.POST('/collections/{id}/palette/{name}', {
      params: { path: { id: t.collection, name: t.name }, query: t.project ? { project: t.project } : {} },
    }),
  )
}

/** Any image that opens the close look when clicked (owner 2026-10-11: click any image for a bigger view). */
export function Zoomable({
  target,
  name,
  children,
  className,
  version,
  imageFilter,
  tools,
}: {
  target: LookTarget
  name: string
  children: ReactNode
  className?: string
  version?: string // a master's version to open on (a post-processing step)
  imageFilter?: string
  tools?: ReactNode
}) {
  const [mode, setMode] = useState<LookMode | null>(null)
  return (
    <>
      <button
        type="button"
        className={`${s.zoomable} ${className ?? ''}`}
        title="Open at 100%"
        aria-label={`Open ${name} at 100%`}
        onClick={(e) => {
          // images sit inside links and selectable rows: the click is the image's alone
          e.preventDefault()
          e.stopPropagation()
          setMode('full')
        }}
      >
        {children}
      </button>
      {mode &&
        createPortal(
          // eslint-disable-next-line jsx-a11y/no-static-element-interactions, jsx-a11y/click-events-have-key-events
          <div onClick={(e) => e.stopPropagation()}>
            <CloseLook
              target={target}
              name={name}
              mode={mode}
              onMode={setMode}
              onClose={() => setMode(null)}
              initialVersion={version}
              imageFilter={imageFilter}
              tools={tools}
            />
          </div>,
          document.body,
        )}
    </>
  )
}

export function CloseLook({
  target,
  name,
  mode,
  onMode,
  onClose,
  initialVersion,
  imageFilter,
  tools,
}: {
  target: LookTarget
  name: string
  mode: LookMode
  onMode: (m: LookMode) => void
  onClose: () => void
  initialVersion?: string
  /** a CSS filter for the image on screen (the sub viewer's display levels, 012-DR-08) */
  imageFilter?: string
  /** controls the caller adds to the bar */
  tools?: ReactNode
}) {
  // zoom like any image viewer (2026-10-15): the wheel or a pinch zooms about the pointer, drag pans, a double
  // click toggles fit and 100%; 'fit' follows the window, a number is the scale (1 = 100%)
  const [zoom, setZoom] = useState<'fit' | number>(1)
  const [annotate, setAnnotate] = useAnnotateSwitch()
  // owner 2026-10-12: tab through a master's versions at 100% — Original, + GraXpert, + BlurXTerminator, + NoiseXTerminator
  // a stitched or stacked master has the same versions (spec 010 US6, 2026-10-24)
  const postId = target.kind === 'master' || target.kind === 'combined' ? target.id : 0
  const post = useQuery({
    queryKey: [target.kind === 'combined' ? 'post-combined' : 'post', postId || -1],
    enabled: postId > 0,
    queryFn: async () =>
      unwrap(
        target.kind === 'combined'
          ? await api.GET('/combined/{id}/post', { params: { path: { id: postId } } })
          : await api.GET('/stacks/{id}/post', { params: { path: { id: postId } } }),
      ),
  })
  const versions = (post.data?.runs[0]?.stages ?? [])
    .filter((st) => st.state === 'done' && st.full)
    .map((st) => ({
      key: `${st.step}`,
      label: `+ ${st.tool_label || st.label}`,
      src: st.full as string,
      stats: st.stats as Stats,
    }))
  const [version, setVersion] = useState(initialVersion ?? 'original')
  const original = post.data?.runs[0]?.original_stats as Stats | undefined
  const shown = versions.find((x) => x.key === version)
  // subs and dataset masters carry a plate solve; combined and palette images don't yet
  const solvable: AnnotateTarget | null =
    target.kind === 'sub' ? target : target.kind === 'master' ? { kind: 'master', id: target.id } : null
  const canAnnotate = solvable !== null
  const q = useQuery({
    queryKey: ['close-look', target],
    queryFn: () => status(target),
    // only poll while a view is being drawn; nothing is started without asking
    refetchInterval: (query) => (query.state.data?.generating ? 1500 : false),
  })
  const qc = useQueryClient()
  // shows Rendering… (and starts polling) on click, as the server will once the worker has it
  const make = useMutation({
    mutationFn: () => generate(target),
    scope: { id: `close-look-${JSON.stringify(target)}` },
    meta: { failed: "Couldn't start the view" },
    ...optimistic<void>(qc, () => [
      [
        ['close-look', target],
        (o) => ({ ...(o as Look), ready: false, generating: true, note: 'Drawing the 100% view…' }),
      ],
    ]),
  })
  // a view that isn't there yet is drawn as soon as it's asked for (owner 2026-10-13): no button to press first.
  // Only an idle "No … view yet" starts one; a failure shows its reason, and "Needs …" notes can't be drawn yet
  const started = useRef(false)
  const idle =
    !!q.data && !q.data.ready && !q.data.generating && !q.data.failed && /^No /.test(q.data.note ?? '')
  useEffect(() => {
    if (idle && !started.current) {
      started.current = true
      make.mutate()
    }
  }, [idle, make])
  const box = useRef<HTMLDivElement>(null)
  const drag = useRef<{ x: number; y: number; l: number; t: number } | null>(null)
  // start in the middle once; switching versions keeps your place (owner 2026-10-12), and the image keeps its size
  // while the next version loads, so the scroll position never collapses
  const centred = useRef(false)
  const [dims, setDims] = useState<{ w: number; h: number } | null>(null)
  // the window's size, watched so "fit" follows it
  const [boxSize, setBoxSize] = useState<{ w: number; h: number } | null>(null)
  useEffect(() => {
    const b = box.current
    if (!b) return
    const ro = new ResizeObserver(() => setBoxSize({ w: b.clientWidth, h: b.clientHeight }))
    ro.observe(b)
    return () => ro.disconnect()
  })
  const fitScale = () => fitOf(boxSize, dims)
  const scale = zoom === 'fit' ? fitScale() : zoom
  /** Zoom to `next`, keeping the image point under (cx, cy) — the pointer, or the middle — where it is. */
  const zoomTo = (next: number, cx?: number, cy?: number) => {
    const b = box.current
    const to = clampZoom(next, fitScale())
    if (!b || !dims) return setZoom(to)
    const r = b.getBoundingClientRect()
    const px = (cx ?? r.left + b.clientWidth / 2) - r.left
    const py = (cy ?? r.top + b.clientHeight / 2) - r.top
    const left = anchoredScroll(b.scrollLeft, px, scale, to)
    const top = anchoredScroll(b.scrollTop, py, scale, to)
    setZoom(to <= fitScale() + 1e-6 ? 'fit' : to)
    requestAnimationFrame(() => {
      b.scrollLeft = left
      b.scrollTop = top
    })
  }
  const zoomBy = (f: number, cx?: number, cy?: number) => zoomTo(scale * f, cx, cy)
  // a non-passive wheel listener, so the page itself doesn't scroll while zooming
  useEffect(() => {
    const b = box.current
    if (!b) return
    const wheel = (e: WheelEvent) => {
      e.preventDefault()
      zoomBy(Math.exp(-e.deltaY * (e.ctrlKey ? 0.01 : 0.002)), e.clientX, e.clientY)
    }
    b.addEventListener('wheel', wheel, { passive: false })
    return () => b.removeEventListener('wheel', wheel)
  })
  useEffect(() => {
    const key = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
      else if (e.key === '1') zoomTo(1)
      else if (e.key === '0') setZoom('fit')
      else if (e.key === '+' || e.key === '=') zoomBy(1.25)
      else if (e.key === '-' || e.key === '_') zoomBy(1 / 1.25)
      else if (e.key.toLowerCase() === 'x') onMode(mode === 'full' ? 'inspector' : 'full')
      else if (e.key.toLowerCase() === 'n' && canAnnotate) setAnnotate(!annotate)
      else if ((e.key === '[' || e.key === ']') && versions.length) {
        const keys = ['original', ...versions.map((x) => x.key)]
        const i = keys.indexOf(version)
        setVersion(keys[(i + (e.key === ']' ? 1 : keys.length - 1)) % keys.length])
      } else return
      e.preventDefault()
      e.stopPropagation()
    }
    window.addEventListener('keydown', key, true)
    return () => window.removeEventListener('keydown', key, true)
  })
  // a 26 MP version takes a moment: say so while it loads (owner 2026-10-13), and fetch the others in the
  // background once the first is up, so later switches are instant
  const d = q.data
  const src = shown ? shown.src : (d?.full ?? '')
  const [loadedSrc, setLoadedSrc] = useState('')
  const loading = !!src && loadedSrc !== src
  const preload = [...versions.map((x) => x.src), d?.full ?? ''].filter(Boolean).join('|')
  const ready = dims !== null
  useEffect(() => {
    if (!ready) return
    for (const url of preload.split('|')) {
      const im = new Image()
      im.src = url
    }
  }, [ready, preload])
  const onImgLoad = (e: { currentTarget: HTMLImageElement }) => {
    const img = e.currentTarget
    setLoadedSrc(img.getAttribute('src') ?? '')
    if (!dims) setDims({ w: img.naturalWidth, h: img.naturalHeight })
    const b = box.current
    if (b && !centred.current) {
      b.scrollLeft = (b.scrollWidth - b.clientWidth) / 2
      b.scrollTop = (b.scrollHeight - b.clientHeight) / 2
      centred.current = true
    }
  }
  return (
    <div className={s.scrim} role="dialog" aria-modal="true" aria-label={`Close look at ${name}`}>
      <div className={s.bar}>
        <strong className={s.name}>{name}</strong>
        <div className={s.group} role="group" aria-label="View">
          <button type="button" aria-pressed={mode === 'full'} onClick={() => onMode('full')}>
            100% view
          </button>
          <button type="button" aria-pressed={mode === 'inspector'} onClick={() => onMode('inspector')}>
            Aberration inspector <kbd>X</kbd>
          </button>
        </div>
        {mode === 'full' && (
          <div className={s.zoom} role="group" aria-label="Zoom">
            <button type="button" onClick={() => zoomBy(1 / 1.25)} aria-label="Zoom out" title="Zoom out (−)">
              −
            </button>
            <span className={s.zoomValue} aria-live="polite">
              {Math.round(scale * 100)}%
            </span>
            <button type="button" onClick={() => zoomBy(1.25)} aria-label="Zoom in" title="Zoom in (+)">
              +
            </button>
            <button
              type="button"
              aria-pressed={zoom === 'fit'}
              onClick={() => setZoom('fit')}
              title="Fit (0)"
            >
              Fit
            </button>
            <button type="button" aria-pressed={zoom === 1} onClick={() => zoomTo(1)} title="100% (1)">
              100%
            </button>
          </div>
        )}
        {mode === 'full' && solvable && (
          <div className={s.group}>
            <AnnotateToggle target={solvable} on={annotate} onChange={setAnnotate} />
            <kbd>N</kbd>
          </div>
        )}
        {tools}
        <button type="button" className={s.close} onClick={onClose}>
          Close <kbd>Esc</kbd>
        </button>
      </div>
      {!d?.ready && !shown && (
        <div className={s.wait} role="status">
          <p>
            {(!d || d.generating || idle) && <Spinner label="Drawing" />} {d?.note || 'Checking…'}
          </p>
          {d?.failed && (
            <button type="button" className={s.close} onClick={() => make.mutate()} disabled={make.isPending}>
              Try again
            </button>
          )}
        </div>
      )}
      {((d?.ready && d.full) || shown) && mode === 'full' && (
        <div className={s.body}>
          <div
            ref={box}
            className={s.pan}
            onDoubleClick={(e) => (zoom === 'fit' ? zoomTo(1, e.clientX, e.clientY) : setZoom('fit'))}
            onMouseDown={(e) => {
              const b = box.current
              if (b) drag.current = { x: e.clientX, y: e.clientY, l: b.scrollLeft, t: b.scrollTop }
            }}
            onMouseMove={(e) => {
              const b = box.current
              if (b && drag.current) {
                b.scrollLeft = drag.current.l - (e.clientX - drag.current.x)
                b.scrollTop = drag.current.t - (e.clientY - drag.current.y)
              }
            }}
            onMouseUp={() => (drag.current = null)}
            onMouseLeave={() => (drag.current = null)}
            role="presentation"
          >
            <span className={s.frame}>
              <img
                src={src}
                alt={`${name}${shown ? `, ${shown.label}` : ''} at full resolution`}
                draggable={false}
                onLoad={onImgLoad}
                style={{
                  ...(dims ? { width: dims.w * scale, height: dims.h * scale } : {}),
                  filter: imageFilter,
                }}
                className={scale >= 2 ? s.actualImg : s.smoothImg}
              />
              {annotate && solvable && <AnnotationOverlay target={solvable} />}
            </span>
            {loading && (
              <div className={s.loading} role="status">
                <Spinner label="Loading" /> Loading{' '}
                {shown ? shown.label.replace(/^\+ /, 'with ') : 'the original'} at full resolution…
              </div>
            )}
          </div>
          {(d?.integration || (original && Object.keys(original).length > 0)) && (
            <div className={s.side}>
              {d?.integration && <IntegrationPanel i={d.integration} />}
              {original && Object.keys(original).length > 0 && (
                <StatsPanel
                  label={shown ? shown.label.replace(/^\+ /, 'With ') : 'Original'}
                  now={shown ? shown.stats : original}
                  original={original}
                />
              )}
            </div>
          )}
        </div>
      )}
      {mode === 'full' && versions.length > 0 && (
        <div className={s.versions} role="tablist" aria-label="Versions">
          {[{ key: 'original', label: 'Original' }, ...versions].map((x) => (
            <button
              key={x.key}
              type="button"
              role="tab"
              aria-selected={version === x.key}
              onClick={() => setVersion(x.key)}
            >
              {x.label}
            </button>
          ))}
          <span className={s.versionsHint}>
            <kbd>[</kbd> <kbd>]</kbd> to switch · same stretch for every version
          </span>
        </div>
      )}
      {d?.ready && mode === 'inspector' && d.inspector && (
        <div className={s.inspect}>
          <img src={d.inspector} alt={`Aberration inspector for ${name}`} style={{ filter: imageFilter }} />
          <p className={s.hint}>Corners, edges and centre at 100%.</p>
        </div>
      )}
    </div>
  )
}

const PART: Record<Integration['kind'], string> = {
  master: '',
  stitch: 'Panels',
  stack: 'Masters stacked',
  palette: 'Filters',
}

/** What the master holds (004-DR-36, 010-DR-30): its integration and subs, and for a stitched or stacked master or
 * a palette, each panel, master or filter it was made from. */
export function IntegrationPanel({ i }: { i: Integration }) {
  const parts = i.parts ?? []
  const left = parts.filter((p) => !p.used)
  return (
    <aside className={s.stats} aria-label="Integration">
      <strong>Integration</strong>
      <dl>
        <div>
          <dt>Total{i.filter ? ` · ${filterName(i.filter)}` : ''}</dt>
          <dd className={s.total}>{integrationText(i.integration_s)}</dd>
        </div>
        <div>
          <dt>Subs</dt>
          <dd>
            {plural(i.subs, 'sub')}
            {i.sessions ? ` · ${plural(i.sessions, 'night')}` : ''}
          </dd>
        </div>
      </dl>
      {parts.length > 0 && (
        <>
          <strong className={s.partsTitle}>{PART[i.kind]}</strong>
          <ul className={s.parts}>
            {parts.map((p, n) => (
              <li key={`${p.label}-${n}`} className={p.used ? undefined : s.unused}>
                <span className={s.partLabel}>
                  {i.kind === 'palette'
                    ? filterName(p.label)
                    : p.panel != null && i.kind === 'stitch'
                      ? `Panel ${p.panel}`
                      : p.label}
                </span>
                <span className={s.partValue}>
                  {integrationText(p.integration_s)} · {plural(p.subs, 'sub')}
                </span>
                {i.kind === 'stitch' && p.panel != null && <span className={s.partNote}>{p.label}</span>}
              </li>
            ))}
          </ul>
          {left.length > 0 && (
            <p className={s.hint}>
              Dimmed: left out, its stars couldn’t be matched to the rest. The total counts only what was
              used.
            </p>
          )}
        </>
      )}
    </aside>
  )
}

type Stats = { background_adu?: number; noise_adu?: number; peak_adu?: number; snr?: number | null }

/** Measurements of the version on screen, against the original stack (owner 2026-10-12). */
function StatsPanel({ label, now, original }: { label: string; now: Stats; original: Stats }) {
  const rows: [keyof Stats, string, number][] = [
    ['background_adu', 'Sky background', 1],
    ['noise_adu', 'Sky noise', 2],
    ['peak_adu', 'Brightest signal', 0],
    ['snr', 'Signal to noise', 0],
  ]
  return (
    <aside className={s.stats} aria-label="Measurements">
      <strong>{label}</strong>
      <dl>
        {rows.map(([k, name, dp]) => {
          const v = now?.[k]
          const o = original?.[k]
          const change = typeof v === 'number' && typeof o === 'number' && o !== 0 ? (v / o - 1) * 100 : null
          return (
            <div key={k}>
              <dt>{name}</dt>
              <dd>
                {typeof v === 'number' ? v.toLocaleString('en-GB', { maximumFractionDigits: dp }) : '—'}
                {k.endsWith('_adu') && typeof v === 'number' ? ' ADU' : ''}
                {change !== null && Math.abs(change) >= 0.5 && now !== original && (
                  <span className={s.delta}>
                    {' '}
                    {change > 0 ? '+' : ''}
                    {numText(change, 0)}%
                  </span>
                )}
              </dd>
            </div>
          )
        })}
      </dl>
      <p className={s.hint}>
        ADU on the 16-bit scale. Noise is measured on the sky, not stars or the galaxy.
      </p>
    </aside>
  )
}
