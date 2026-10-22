// One observing night at one place (T101, spec 012): where it was shot, the Moon, the sky as it was shot (spec 015:
// every sub where its target stood, with a slider through the night), every sub that night as thumbnails per dataset
// (they open in the viewer, stepping through them in the order the strips show), and the calibration frames taken.
import { useQuery } from '@tanstack/react-query'
import { getRouteApi, Link, useNavigate } from '@tanstack/react-router'
import { useMemo } from 'react'
import { api, unwrap } from '../../api/client'
import type { components } from '../../api/schema'
import { glanceUrl } from '../../components/Glance'
import { Modal } from '../../components/Modal'
import { EmptyState, ErrorState, PageLoading } from '../../components/ui'
import { useSort } from '../../components/sortable'
import {
  clockSpan,
  clockText,
  countText,
  exposureText,
  integrationText,
  nightText,
  pctText,
  shutterSpan,
} from '../format'
import { SiteMap } from '../map/SiteMap'
import { usePlaceName } from '../map/place'
import { moonSummary, SkyTable, SkyTracks, SkyView, useNightSky } from '../sky/SkyView'
import { SubView } from '../sub/SubDetail'
import v from '../v2/v2.module.css'
import tb from '../library/tables.module.css'
import s from './night.module.css'
import { forNight, omit, readScope, scopeQuery } from '../scope/scope'

const route = getRouteApi('/app/nights/$date')
type Sub = components['schemas']['SubOut']
type Night = components['schemas']['NightOut']

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
const VERDICT: Record<string, string> = { accept: s.accept, down: s.down, reject: s.reject }

export function NightView() {
  const { date } = route.useParams()
  const search = route.useSearch()
  const navigate = useNavigate()
  const q = useQuery({
    queryKey: ['night', date, search.site ?? ''],
    queryFn: async () =>
      unwrap(await api.GET('/nights/{date}', { params: { path: { date }, query: { site: search.site } } })),
    retry: false,
  })
  const site = q.data?.site_key
  // the scope a link brought (spec 018), carried on to the map, the nights either side and What to shoot
  const carry = scopeQuery(omit(readScope(search), 'site'))
  const subsQ = useQuery({
    queryKey: ['night-subs', date, site],
    enabled: !!site,
    queryFn: async () =>
      unwrap(await api.GET('/nights/{date}/subs', { params: { path: { date }, query: { site: site! } } })),
  })
  const skyQ = useNightSky(date, site)
  const byDataset = useMemo(() => {
    const m = new Map<number, Sub[]>()
    for (const x of subsQ.data ?? []) {
      if (x.dataset_id == null) continue
      m.set(x.dataset_id, [...(m.get(x.dataset_id) ?? []), x])
    }
    return m
  }, [subsQ.data])
  const open = (sha?: string) =>
    void navigate({
      to: '/nights/$date',
      params: { date },
      search: { ...search, sub: sha },
      replace: !!search.sub,
    })

  if (q.isError)
    return (
      <ErrorState title={`Night of ${nightText(date)}`} onRetry={() => q.refetch()}>
        {q.error.message}
      </ErrorState>
    )
  const n = q.data
  if (!n) return <PageLoading />
  const subs = n.datasets.reduce((a, d) => a + d.sub_count, 0)
  const integ = n.datasets.reduce((a, d) => a + d.integration_s, 0)
  // One order for the grid and the viewer: dataset by dataset, as the strips show them, so Next is the sub to the right
  const order = n.datasets.flatMap((d) => (byDataset.get(d.dataset.id) ?? []).map((x) => x.sha256))
  // one convention for every block's times (B17): first shutter open to last shutter close, to the minute
  const span = (list: Sub[] | undefined, first?: string | null, last?: string | null) => {
    const sp = list?.length ? shutterSpan(list) : null
    return sp ? clockSpan(sp[0], sp[1]) : first && last ? clockSpan(first, last) : ''
  }
  const nightSpan = span(subsQ.data, n.first_utc, n.last_utc)
  // the Moon from one source (B18): the sky's, during the lights, when it's known
  const moon = skyQ.data?.moon ? moonSummary(skyQ.data).split(' · ') : null
  return (
    <div className={v.page}>
      <header className={v.head}>
        <div>
          <div className={v.crumbs}>
            <Link to="/map" search={carry}>
              Map
            </Link>{' '}
            / Night
          </div>
          <h1>{nightText(n.date)}</h1>
          <div className={v.sub}>
            <Place n={n} />
            {nightSpan ? ` · ${nightSpan}` : ''}
          </div>
        </div>
        <nav className={v.actions} aria-label="Other nights, and what to shoot">
          {n.previous && (
            <Link
              to="/nights/$date"
              params={{ date: n.previous }}
              search={{ ...carry, site }}
              className={v.pill}
            >
              ← {nightText(n.previous)}
            </Link>
          )}
          {n.next && (
            <Link to="/nights/$date" params={{ date: n.next }} search={{ ...carry, site }} className={v.pill}>
              {nightText(n.next)} →
            </Link>
          )}
          <Link
            to="/calibration/to-shoot"
            search={forNight(readScope(search), n.date, site)}
            className={v.pill}
            title="The calibration frames that would release this night's waiting subs"
          >
            What to shoot
          </Link>
        </nav>
      </header>

      {n.sites.length > 1 && (
        <div className={v.pills} role="group" aria-label="Place">
          <span className={v.muted}>Shot in {n.sites.length} places this night:</span>
          {n.sites.map((k) => (
            <Link
              key={k}
              to="/nights/$date"
              params={{ date }}
              search={{ ...carry, site: k }}
              className={v.pill}
              aria-current={k === site ? 'page' : undefined}
            >
              {k}
            </Link>
          ))}
        </div>
      )}

      <div className={`${v.readouts} ${s.readouts}`}>
        <div className={v.readout}>
          <div className={v.readoutLabel}>Integration</div>
          <div className={v.readoutValue}>{integrationText(integ)}</div>
          <div className={v.readoutDetail}>
            {countText(subs)} subs in {n.datasets.length} dataset
            {n.datasets.length === 1 ? '' : 's'}
          </div>
        </div>
        <div className={v.readout}>
          <div className={v.readoutLabel}>Moon</div>
          <div className={v.readoutValue}>
            {moon ? moon[0].replace(' lit', '') : n.moon ? pctText(n.moon.illumination) : 'Not known'}
          </div>
          <div className={v.readoutDetail}>
            {moon
              ? `${moon[1]} during the lights`
              : !n.moon
                ? 'no lights with a time'
                : n.moon.up_during_lights == null
                  ? 'lit; where it was shot isn’t recorded'
                  : n.moon.up_during_lights
                    ? 'up during the lights'
                    : 'below the horizon during the lights'}
          </div>
        </div>
        <div className={v.readout}>
          <div className={v.readoutLabel}>Calibration</div>
          <div className={v.readoutValue}>{n.calibration_sets.length}</div>
          <div className={v.readoutDetail}>
            set{n.calibration_sets.length === 1 ? '' : 's'} taken this night
          </div>
        </div>
      </div>

      <section className={`${v.card} ${v.cardPad}`} aria-label="Through the night">
        <h2 className={v.sectionLabel}>Through the night</h2>
        <div className={s.skyBody}>
          {skyQ.data ? (
            <SkyView sky={skyQ.data} onOpen={(sha) => open(sha)} />
          ) : skyQ.isError ? (
            <Timeline n={n} />
          ) : (
            <p className={v.muted}>{site ? 'Working out where each sub was on the sky…' : ''}</p>
          )}
        </div>
      </section>

      <div className={v.twoCol}>
        <section className={`${v.card} ${v.cardPad}`} aria-label="Tracks">
          <h2 className={v.sectionLabel}>Tracks</h2>
          <div className={s.skyBody}>
            {skyQ.data ? <SkyTracks sky={skyQ.data} /> : <Timeline n={n} />}
            {skyQ.data && <SkyTable sky={skyQ.data} onOpen={(sha) => open(sha)} />}
          </div>
        </section>
        {n.lat != null && n.lon != null ? (
          <section className={`${v.card} ${v.cardPad}`} aria-label="Where">
            <SiteMap lat={n.lat} lon={n.lon} night={n.date} />
          </section>
        ) : (
          <section className={`${v.card} ${v.cardPad} ${v.muted}`}>
            These subs don’t record where they were shot.
          </section>
        )}
      </div>

      {n.datasets.length === 0 ? (
        <EmptyState title="No lights this night">Calibration frames only.</EmptyState>
      ) : (
        n.datasets.map((d) => {
          const list = byDataset.get(d.dataset.id) ?? []
          return (
            <section key={d.dataset.id} className={v.card}>
              <header className={s.dsHead}>
                <div>
                  <Link
                    to="/datasets/$id"
                    params={{ id: String(d.dataset.id) }}
                    search={{ tab: 'subs', night: n.date }}
                    className={s.dsName}
                  >
                    {d.dataset.display_name}
                  </Link>
                  <div className={v.muted}>
                    {[d.dataset.rig, span(list, d.first_utc, d.last_utc)].filter(Boolean).join(' · ')}
                    {d.user_rejected_count > 0 ? ` · ${d.user_rejected_count} rejected in NINA` : ''}
                  </div>
                </div>
                <div className={s.dsFigures}>
                  <span className={v.mono}>{integrationText(d.integration_s)}</span>
                  <span className={v.muted}>{countText(d.sub_count)} subs</span>
                </div>
              </header>
              <ul className={s.strip} aria-label={`Subs of ${d.dataset.display_name}`}>
                {list.map((x) => (
                  <li key={x.sha256}>
                    <button
                      type="button"
                      className={`${s.thumb} ${VERDICT[x.verdict ?? ''] ?? ''}`}
                      onClick={() => open(x.sha256)}
                      aria-label={`Open ${x.file}`}
                      title={x.file}
                    >
                      <img src={glanceUrl(x.sha256)} alt="" loading="lazy" />
                    </button>
                    {x.time && <span className={s.thumbTime}>{clockText(x.time)}</span>}
                  </li>
                ))}
                {subsQ.isPending && <li className={v.muted}>Loading subs…</li>}
              </ul>
            </section>
          )
        })
      )}

      <Calibration n={n} />
      {Object.keys(n.other_frames).length > 0 && (
        <p className={v.muted}>
          Also:{' '}
          {Object.entries(n.other_frames)
            .map(([t, k]) => `${k} ${(TYPE[t] ?? t).toLowerCase()}`)
            .join(', ')}
          .
        </p>
      )}

      {search.sub && (
        <Modal label="Sub" onClose={() => open(undefined)}>
          <SubView
            sha={search.sub}
            list={{
              shas: order.includes(search.sub) ? order : [search.sub],
              label: `Every sub on ${nightText(n.date)}`,
              onPick: (sha) => open(sha),
              onClose: () => open(undefined),
            }}
          />
        </Modal>
      )}
    </div>
  )
}

function Place({ n }: { n: Night }) {
  const name = usePlaceName(n.lat ?? null, n.lon ?? null)
  if (n.lat == null || n.lon == null) return <>Place not recorded</>
  return <>{name.data ?? 'Finding the place…'}</>
}

/** A bar per dataset across the night's span, so you see what was shot when (and the gaps). */
function Timeline({ n }: { n: Night }) {
  const rows = n.datasets.filter((d) => d.first_utc && d.last_utc)
  if (!n.first_utc || !n.last_utc || !rows.length) return <p className={v.muted}>No times recorded.</p>
  const t0 = Date.parse(n.first_utc)
  const span = Math.max(Date.parse(n.last_utc) - t0, 60_000)
  const pct = (iso: string) => ((Date.parse(iso) - t0) / span) * 100
  return (
    <div className={s.timeline}>
      {rows.map((d) => {
        const left = pct(d.first_utc!)
        const width = Math.max(pct(d.last_utc!) - left, 0.8)
        return (
          <div key={d.dataset.id} className={s.lane}>
            <span className={s.laneName} title={d.dataset.display_name}>
              {d.dataset.display_name}
            </span>
            <span className={s.track}>
              <span
                className={s.bar}
                style={{ left: `${left}%`, width: `${width}%` }}
                title={`${clockSpan(d.first_utc, d.last_utc)} · ${d.sub_count} subs`}
              />
            </span>
          </div>
        )
      })}
      <div className={s.axis}>
        <span>{clockText(n.first_utc)}</span>
        <span>{clockText(n.last_utc)}</span>
      </div>
    </div>
  )
}

function Calibration({ n }: { n: Night }) {
  const { sorted, th } = useSort(n.calibration_sets, {
    type: (c) => TYPE[c.type] ?? c.type,
    filter: (c) => c.filter ?? Object.keys(c.filter_blocks).join(' '),
    exposure: (c) => c.exptime_s,
    frames: (c) => c.frame_count,
    session: (c) => c.session_start_utc,
  })
  if (!n.calibration_sets.length) return null
  return (
    <section className={v.card} aria-label="Calibration">
      <h2 className={`${v.sectionLabel} ${s.tableTitle}`}>Calibration taken this night</h2>
      <div className={tb.pane}>
        <table className={`${v.table} ${tb.table} cards`}>
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
            {sorted.map((c) => (
              <tr key={c.id}>
                <td>
                  <Link to="/calibration/sets/$id" params={{ id: String(c.id) }}>
                    {TYPE[c.type] ?? c.type}
                  </Link>
                </td>
                <td data-label="Filter">
                  {c.filter ??
                    Object.entries(c.filter_blocks)
                      .map(([f, k]) => `${f} ×${k}`)
                      .join(', ')}
                </td>
                <td className={`${v.mono} ${tb.num}`} data-label="Exposure">
                  {exposureText(c.exptime_s)}
                </td>
                <td className={`${v.mono} ${tb.num}`} data-label="Frames">
                  {c.frame_count}
                </td>
                <td className={`${v.mono} ${tb.num}`} data-label="Session">
                  {clockText(c.session_start_utc) === clockText(c.session_end_utc)
                    ? clockText(c.session_start_utc)
                    : clockSpan(c.session_start_utc, c.session_end_utc)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  )
}
