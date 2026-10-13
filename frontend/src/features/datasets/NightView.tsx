// One observing night (T101): every dataset and calibration set catalogued that night.
import { useQuery } from '@tanstack/react-query'
import { getRouteApi, Link } from '@tanstack/react-router'
import { api, unwrap } from '../../api/client'
import { EmptyState, ErrorState } from '../../components/ui'
import { integrationText, nightText, timeText } from '../format'
import ui from '../../components/ui.module.css'
import s from './datasets.module.css'
import { useSort } from '../../components/sortable'
import { Collapsible } from '../../components/Collapsible'
import tb from '../library/tables.module.css'

const route = getRouteApi('/app/nights/$date')

const TYPE: Record<string, string> = {
  flat: 'Flats',
  dark: 'Darks',
  dark_flat: 'Dark flats',
  bias: 'Bias',
  master_dark: 'Master darks',
  master_flat: 'Master flats',
  master_bias: 'Master bias',
  unknown: 'Unknown type',
  light: 'Lights not in a dataset',
}

export function NightView() {
  const { date } = route.useParams()
  const q = useQuery({
    queryKey: ['night', date],
    queryFn: async () => unwrap(await api.GET('/nights/{date}', { params: { path: { date } } })),
    retry: false,
  })
  const { sorted: calSets, th } = useSort(q.data?.calibration_sets ?? [], {
    type: (c) => TYPE[c.type] ?? c.type,
    filter: (c) => c.filter ?? Object.keys(c.filter_blocks).join(' '),
    exposure: (c) => c.exptime_s,
    frames: (c) => c.frame_count,
    session: (c) => c.session_start_utc,
  })
  if (q.isError)
    return (
      <ErrorState title={`Night of ${nightText(date)}`} onRetry={() => q.refetch()}>
        {q.error.message}
      </ErrorState>
    )
  const n = q.data
  if (!n) return null
  const subs = n.datasets.reduce((a, d) => a + d.sub_count, 0)
  const integ = n.datasets.reduce((a, d) => a + d.integration_s, 0)
  return (
    <div className={s.page}>
      <header className={s.header}>
        <span className="label">Night</span>
        <h1>{nightText(n.date)}</h1>
        <div className={`${s.subtitle} muted`}>
          {n.datasets.length} dataset{n.datasets.length === 1 ? '' : 's'} · {subs} subs ·{' '}
          {integrationText(integ)}
          {n.calibration_sets.length > 0 &&
            ` · ${n.calibration_sets.length} calibration set${n.calibration_sets.length === 1 ? '' : 's'}`}
        </div>
        <nav className={s.nightNav} aria-label="Other nights">
          {n.previous ? (
            <Link to="/nights/$date" params={{ date: n.previous }}>
              ← {nightText(n.previous)}
            </Link>
          ) : (
            <span />
          )}
          {n.next && (
            <Link to="/nights/$date" params={{ date: n.next }}>
              {nightText(n.next)} →
            </Link>
          )}
        </nav>
      </header>

      <Collapsible id="night-datasets" title="Datasets" meta={n.datasets.length}>
        {n.datasets.length === 0 ? (
          <EmptyState title="No lights this night">Calibration frames only.</EmptyState>
        ) : (
          <ul className={s.list}>
            {n.datasets.map((d) => (
              <li key={d.dataset.id}>
                <Link to="/datasets/$id" params={{ id: String(d.dataset.id) }} className={s.row}>
                  <div className={s.title}>
                    <span className={s.target}>{d.dataset.target}</span>
                    <span className="muted">
                      {[d.dataset.panel != null ? `Panel ${d.dataset.panel}` : null, d.dataset.filter]
                        .filter(Boolean)
                        .join(' · ')}
                    </span>
                  </div>
                  <div className={`${s.figure} mono`}>{integrationText(d.integration_s)}</div>
                  <div className={`${s.figure} mono`}>
                    {d.sub_count} <span className="muted">subs</span>
                  </div>
                  <div className="muted">
                    {d.first_utc && d.last_utc ? `${timeText(d.first_utc)}–${timeText(d.last_utc)}` : ''}
                  </div>
                  <div className="muted">
                    {d.user_rejected_count > 0 ? `${d.user_rejected_count} rejected in NINA` : ''}
                  </div>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </Collapsible>

      {n.calibration_sets.length > 0 && (
        <Collapsible id="night-calibration" title="Calibration" meta={n.calibration_sets.length}>
          <div className={`${s.tableWrap} ${tb.pane}`}>
            <table className={`${ui.table} ${tb.table}`}>
              <thead>
                <tr>
                  {th('type', 'Type')}
                  {th('filter', 'Filter')}
                  {th('exposure', 'Exposure', tb.num)}
                  {th('frames', 'Frames', tb.num)}
                  {th('session', 'Session', tb.num)}
                </tr>
              </thead>
              <tbody>
                {calSets.map((c) => (
                  <tr key={c.id}>
                    <td>{TYPE[c.type] ?? c.type}</td>
                    <td>
                      {c.filter ??
                        Object.entries(c.filter_blocks)
                          .map(([f, k]) => `${f} ×${k}`)
                          .join(', ')}
                    </td>
                    <td className={`mono ${tb.num}`}>{c.exptime_s} s</td>
                    <td className={`mono ${tb.num}`}>{c.frame_count}</td>
                    <td className={`mono ${tb.num}`}>
                      {timeText(c.session_start_utc)}–{timeText(c.session_end_utc)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Collapsible>
      )}
      {Object.keys(n.other_frames).length > 0 && (
        <p className="muted">
          Also:{' '}
          {Object.entries(n.other_frames)
            .map(([t, k]) => `${k} ${(TYPE[t] ?? t).toLowerCase()}`)
            .join(', ')}
          .
        </p>
      )}
    </div>
  )
}
