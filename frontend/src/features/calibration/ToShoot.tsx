// What to shoot (spec 017): the lights waiting for calibration, as the darks, biases and flats that would release
// them, biggest win first. Darks and biases download as a NINA sequence; flats are listed with their nights, to be
// shot with the rig as it was then.
import { useQuery } from '@tanstack/react-query'
import { Link } from '@tanstack/react-router'
import { useState } from 'react'
import { api, unwrap } from '../../api/client'
import type { components } from '../../api/schema'
import { Collapsible } from '../../components/Collapsible'
import { EmptyState, ErrorState, PageLoading } from '../../components/ui'
import { integrationText, nightText } from '../format'
import v from '../v2/v2.module.css'
import s from './toShoot.module.css'

type Need = components['schemas']['NeedOut']
type Ref = components['schemas']['DatasetRef']

const subsText = (n: number) => `${n.toLocaleString('en-GB')} sub${n === 1 ? '' : 's'}`
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

export function ToShoot() {
  const q = useQuery({
    queryKey: ['calibration-shopping'],
    queryFn: async () => unwrap(await api.GET('/calibration/shopping')),
  })
  const [frames, setFrames] = useState(30)
  if (q.isPending) return <PageLoading />
  if (q.isError) return <ErrorState title="Couldn’t load what to shoot">{q.error.message}</ErrorState>
  const { needs, others } = q.data
  const darks = needs.filter((n) => n.kind === 'dark' || n.kind === 'bias')
  const flats = needs.filter((n) => n.kind === 'flat')
  const n = Math.max(1, Math.min(500, frames || 1))
  return (
    <div className={s.page}>
      <p className={s.crumbs}>
        <Link to="/calibration">Calibration</Link> / What to shoot
      </p>
      <header className={s.head}>
        <div>
          <h1>What to shoot</h1>
          <p className="muted">
            The calibration frames that would release the subs waiting for calibration, biggest win first.
          </p>
        </div>
      </header>

      {!needs.length && !others.length && (
        <EmptyState title="Nothing to shoot">Every sub has the calibration it needs.</EmptyState>
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
            <a className={v.pill} href={`/api/v1/calibration/shopping/nina.xml?frames=${n}`} download>
              Download NINA sequence
            </a>
            <a className={v.pill} href={`/api/v1/calibration/shopping.csv?frames=${n}`} download>
              Download CSV
            </a>
            <span className="muted">
              NINA can't change the cooling per row: rows run coldest first, each with its temperature.
            </span>
          </div>
          <div className={s.scroll}>
            <table className={s.table}>
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
                    <td>{d.camera || 'Unknown camera'}</td>
                    <td className={v.mono}>{d.kind === 'bias' ? '–' : temp(d.temp_c)}</td>
                    <td className={v.mono}>
                      {[gainText(d), `bin ${d.xbin}`, d.size].filter(Boolean).join(' · ')}
                    </td>
                    <td className={v.mono}>
                      {subsText(d.subs)} · {integrationText(d.integration_s)}
                    </td>
                    <td>
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
            A flat belongs to the rig as it was that night (focus, rotation, dust), so these are yours to
            shoot: on or before the night, without changing the rig in between.
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
