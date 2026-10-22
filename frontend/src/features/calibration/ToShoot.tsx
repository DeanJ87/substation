// What to shoot (spec 017): the lights waiting for calibration, as the darks, biases and flats that would release
// them, biggest win first. Darks and biases download as a NINA sequence; flats are listed with their nights, to be
// shot with the rig as it was then.
import { useQuery } from '@tanstack/react-query'
import { getRouteApi, Link, useNavigate } from '@tanstack/react-router'
import { useState } from 'react'
import { api, unwrap } from '../../api/client'
import type { components } from '../../api/schema'
import { Collapsible } from '../../components/Collapsible'
import { EmptyState, ErrorState, PageLoading } from '../../components/ui'
import { countText, integrationText, nightText } from '../format'
import { ScopeBar } from '../scope/ScopeBar'
import { scopeParams, scopeQuery } from '../scope/scope'
import v from '../v2/v2.module.css'
import s from './toShoot.module.css'
import { Help } from '../../components/Help'

type Need = components['schemas']['NeedOut']
type Ref = components['schemas']['DatasetRef']

const subsText = (n: number) => `${countText(n)} sub${n === 1 ? '' : 's'}`
const temp = (t: number | null | undefined) => (t == null ? 'uncooled' : `${t} °C`)
const gainText = (n: Need) =>
  [n.gain != null ? `gain ${n.gain}` : '', n.offset != null ? `offset ${n.offset}` : '']
    .filter(Boolean)
    .join(' · ')

function Datasets({ list }: { list: Ref[] }) {
  const shown = list.slice(0, 3)
  return (
    <span className={s.datasets}>
      {shown.map((d, i) => (
        <span key={d.id}>
          {i > 0 && ', '}
          <Link to="/datasets/$id" params={{ id: String(d.id) }} search={{ tab: 'calibration' }}>
            {d.label}
          </Link>
        </span>
      ))}
      {list.length > 3 && ` and ${list.length - 3} more`}
    </span>
  )
}

function nightsText(nights: string[]) {
  if (nights.length <= 3) return nights.map(nightText).join(', ')
  return `${nightText(nights[0])} to ${nightText(nights[nights.length - 1])} (${nights.length} nights)`
}

const route = getRouteApi('/app/calibration/to-shoot')

export function ToShoot() {
  const scope = route.useSearch()
  const navigate = useNavigate()
  const q = useQuery({
    queryKey: ['calibration-shopping', scope],
    queryFn: async () =>
      unwrap(await api.GET('/calibration/shopping', { params: { query: scopeQuery(scope) } })),
    placeholderData: (prev) => prev,
  })
  const [frames, setFrames] = useState(30)
  if (q.isPending) return <PageLoading />
  if (q.isError) return <ErrorState title="Couldn’t load what to shoot">{q.error.message}</ErrorState>
  const { needs, others } = q.data
  const darks = needs.filter((n) => n.kind === 'dark' || n.kind === 'bias')
  const flats = needs.filter((n) => n.kind === 'flat')
  const n = Math.max(1, Math.min(500, frames || 1))
  const narrowed = scopeParams(scope)
  const also = narrowed ? `&${narrowed}` : ''
  return (
    <div className={s.page}>
      <p className={s.crumbs}>
        <Link to="/calibration" search={scopeQuery(scope)}>
          Calibration
        </Link>{' '}
        / What to shoot
      </p>
      <header className={s.head}>
        <div>
          <h1>What to shoot</h1>
          <p className="muted">What would release the subs waiting for calibration, biggest win first.</p>
        </div>
      </header>
      <ScopeBar
        scope={scope}
        filters={[...new Set(needs.filter((x) => x.filter).map((x) => x.filter))]}
        onChange={(next) => void navigate({ to: '/calibration/to-shoot', search: next, replace: true })}
      />

      {!needs.length && !others.length && (
        <EmptyState title="Nothing to shoot">
          {narrowed ? 'Nothing waiting within these filters.' : 'Every sub has the calibration it needs.'}
        </EmptyState>
      )}

      {darks.length > 0 && (
        <Collapsible
          id="to-shoot-darks"
          title="Darks and bias"
          meta={subsText(darks.reduce((t, x) => t + x.subs, 0))}
        >
          <div className={s.exportBar}>
            <label>
              Frames each{' '}
              <input
                type="number"
                min={1}
                max={500}
                value={frames}
                onChange={(e) => setFrames(Number(e.target.value))}
                className={s.num}
              />
            </label>
            <a className={v.pill} href={`/api/v1/calibration/shopping/nina.xml?frames=${n}${also}`} download>
              Download NINA sequence
            </a>
            <a className={v.pill} href={`/api/v1/calibration/shopping.csv?frames=${n}${also}`} download>
              Download CSV
            </a>
            <span className="muted">
              NINA can't change the cooling per row: rows run coldest first, each with its temperature.
            </span>
          </div>
          <div className={s.scroll}>
            <table className={`${s.table} cards`}>
              <thead>
                <tr>
                  <th scope="col">Frame</th>
                  <th scope="col">Camera</th>
                  <th scope="col">Cool to</th>
                  <th scope="col">Settings</th>
                  <th scope="col">Releases</th>
                  <th scope="col">For</th>
                </tr>
              </thead>
              <tbody>
                {darks.map((d) => (
                  <tr
                    key={`${d.kind}-${d.camera}-${d.exptime_s}-${d.gain}-${d.offset}-${d.xbin}-${d.temp_c}-${d.size}`}
                  >
                    <td>
                      <strong>{d.kind === 'bias' ? 'Bias' : `${d.exptime_s} s dark`}</strong>
                    </td>
                    <td data-label="Camera">{d.camera || 'Unknown camera'}</td>
                    <td className={v.mono} data-label="Cool to">
                      {d.kind === 'bias' ? '–' : temp(d.temp_c)}
                    </td>
                    <td className={v.mono} data-label="Settings" data-wide>
                      {[gainText(d), `bin ${d.xbin}`, d.size].filter(Boolean).join(' · ')}
                    </td>
                    <td className={v.mono} data-label="Releases">
                      {subsText(d.subs)} · {integrationText(d.integration_s)}
                    </td>
                    <td data-label="For" data-wide>
                      <Datasets list={d.datasets} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Collapsible>
      )}

      {flats.length > 0 && (
        <Collapsible id="to-shoot-flats" title="Flats" meta={subsText(flats.reduce((t, x) => t + x.subs, 0))}>
          <p className="muted">
            Shoot on or before the night, without changing the rig in between.{' '}
            <Help topic="Why flats can't wait">
              A flat belongs to the rig as it was that night (focus, rotation, dust).
            </Help>
          </p>
          <ul className={s.flatList}>
            {flats.map((f) => (
              <li key={`${f.camera}-${f.telescope}-${f.filter}-${f.xbin}-${f.size}`}>
                <div>
                  <strong>
                    {f.filter || 'No filter'} flats · {[f.telescope, f.camera].filter(Boolean).join(' + ')}
                  </strong>
                  <div className="muted">
                    For {nightsText(f.nights)} · bin {f.xbin}
                    {f.size ? ` · ${f.size}` : ''}
                  </div>
                </div>
                <div className={s.flatSide}>
                  <span className={v.mono}>
                    {subsText(f.subs)} · {integrationText(f.integration_s)}
                  </span>
                  <Datasets list={f.datasets} />
                </div>
              </li>
            ))}
          </ul>
        </Collapsible>
      )}

      {others.length > 0 && (
        <Collapsible
          id="to-shoot-other"
          title="Waiting on something else"
          meta={subsText(others.reduce((t, x) => t + x.subs, 0))}
        >
          <ul className={s.flatList}>
            {others.map((o) => (
              <li key={o.reason}>
                <div>
                  <strong>{o.reason.charAt(0).toUpperCase() + o.reason.slice(1)}</strong>
                </div>
                <div className={s.flatSide}>
                  <span className={v.mono}>{subsText(o.subs)}</span>
                  <Datasets list={o.datasets} />
                </div>
              </li>
            ))}
          </ul>
        </Collapsible>
      )}
    </div>
  )
}
