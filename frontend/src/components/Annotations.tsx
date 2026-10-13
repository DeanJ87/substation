// Annotations (009 amendment 2026-10-12, owner): the named objects in a plate-solved
// field — Messier, NGC, IC, Sharpless, LDN dark nebulae and bright stars — drawn over its preview. Positions come
// from the solve, as shares of the preview's width and height, so the overlay fits any size the image is shown at.
import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { api, unwrap } from '../api/client'
import type { components } from '../api/schema'
import s from './Annotations.module.css'

type Annotations = components['schemas']['AnnotationsOut']
type Obj = components['schemas']['AnnotationOut']
export type AnnotateTarget = { kind: 'sub'; sha: string } | { kind: 'master'; id: number }

const KEY = 'sst-annotate'

/** Whether annotations are on: one switch for every preview, remembered on this browser. */
export function useAnnotateSwitch(): [boolean, (on: boolean) => void] {
  const [on, set] = useState(() => {
    try {
      return localStorage.getItem(KEY) === '1'
    } catch {
      return false
    }
  })
  return [
    on,
    (next) => {
      set(next)
      try {
        localStorage.setItem(KEY, next ? '1' : '0')
      } catch {
        /* private window: the switch still works for this page */
      }
    },
  ]
}

export function useAnnotations(target: AnnotateTarget, enabled = true) {
  return useQuery({
    queryKey: ['annotations', target],
    enabled,
    staleTime: Infinity, // a solve's objects don't move
    queryFn: async (): Promise<Annotations> =>
      target.kind === 'sub'
        ? unwrap(await api.GET('/frames/{sha256}/annotations', { params: { path: { sha256: target.sha } } }))
        : unwrap(await api.GET('/stacks/{id}/annotations', { params: { path: { id: target.id } } })),
  })
}

/** "NGC7000" → "NGC 7000", "LdN-1356" → "LDN 1356"; Siril's lists squash the catalogue and number together. */
export function displayName(o: Pick<Obj, 'name' | 'kind'>): string {
  if (o.kind === 'ngc' || o.kind === 'ic') return o.name.replace(/^(NGC|IC)(\d)/, '$1 $2')
  if (o.kind === 'ldn') return o.name.replace(/^LdN-/, 'LDN ')
  if (o.kind === 'messier') return o.name.replace(/^M(\d)/, 'M $1')
  return o.name
}

/** A common name from the aliases, if there is one ("Andromeda galaxy"), not another catalogue number. */
function commonName(o: Obj): string {
  const names = (o.alias ?? '').split('/').map((a) => a.trim())
  return names.find((a) => a && !/^(NGC|IC|Sh2|LdN|M|Mel|Cr|HD|HIP)[\s-]?\d/i.test(a)) ?? ''
}

const LIMIT = 40 // a crowded field (Orion) has hundreds; the list arrives most notable first

/** The overlay: place inside a `position: relative` box that is exactly the image's size. */
export function AnnotationOverlay({ target }: { target: AnnotateTarget }) {
  const q = useAnnotations(target)
  const objs = q.data?.objects.slice(0, LIMIT) ?? []
  // labels of close neighbours (NGC 2959 and 2959A) would print on top of each other: each one steps down until
  // clear of those placed before it (most notable first)
  const placed: { u: number; v: number }[] = []
  const labelAt = (u: number, v: number) => {
    let lv = v
    for (let n = 0; n < 6 && placed.some((p) => Math.abs(p.u - u) < 0.12 && Math.abs(p.v - lv) < 0.022); n++)
      lv += 0.025
    placed.push({ u, v: lv })
    return lv
  }
  return (
    <div className={s.layer} aria-label="Annotations" role="list">
      {objs.map((o) => {
        const big = (o.size ?? 0) > 0.03
        const label = commonName(o)
        // an object only partly in view is labelled where it comes in
        const u = Math.min(0.98, Math.max(0.01, o.u))
        const v = labelAt(u, Math.min(0.97, Math.max(0.01, o.v)))
        return (
          <div key={o.name} role="listitem" className={`${s.obj} ${s[o.kind] ?? ''}`}>
            {big ? (
              <span
                className={s.ring}
                style={{ left: `${o.u * 100}%`, top: `${o.v * 100}%`, width: `${(o.size ?? 0) * 100}%` }}
              />
            ) : (
              <span className={s.dot} style={{ left: `${o.u * 100}%`, top: `${o.v * 100}%` }} />
            )}
            <span
              className={`${s.label} ${u > 0.75 ? s.flip : ''} ${v > 0.9 ? s.up : ''}`}
              style={{ left: `${u * 100}%`, top: `${v * 100}%` }}
            >
              {displayName(o)}
              {label && <span className={s.common}> · {label}</span>}
            </span>
          </div>
        )
      })}
    </div>
  )
}

/** The on/off pill, with what it will show (or why it can't). */
export function AnnotateToggle({
  target,
  on,
  onChange,
  className,
}: {
  target: AnnotateTarget
  on: boolean
  onChange: (on: boolean) => void
  className?: string
}) {
  const q = useAnnotations(target)
  const n = q.data?.objects.length ?? 0
  const solved = q.data?.solved ?? false
  return (
    <button
      type="button"
      className={className}
      aria-pressed={on && solved}
      disabled={!solved}
      title={
        q.isLoading
          ? 'Checking the plate solve…'
          : solved
            ? `Label the ${n} catalogued object${n === 1 ? '' : 's'} in this field`
            : q.data?.note || 'Not plate solved'
      }
      onClick={() => onChange(!on)}
    >
      Annotate{solved && n ? ` · ${n}` : ''}
    </button>
  )
}
