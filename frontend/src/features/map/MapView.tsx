// The map (spec 012): every place subs were shot, as a picture with a count that merges with its neighbours as you
// zoom out, like a phone's photo map. Choosing a place lists its nights; a night opens the night page. The address
// can say where to look and which nights to show (spec 015): a night page opens it at its place, on its night.
import 'leaflet/dist/leaflet.css'
import { useQuery } from '@tanstack/react-query'
import { getRouteApi, Link, useNavigate } from '@tanstack/react-router'
import L from 'leaflet'
import './leafletGlobal'
import 'leaflet.markercluster'
import { useEffect, useRef, useState } from 'react'
import { api, unwrap } from '../../api/client'
import type { components } from '../../api/schema'
import { useAppTheme } from '../../design/ThemeContext'
import { coords, usePlaceName } from './place'
import { type MapSearch, nearest, period, periodText, presets } from './search'
import { baseLayer } from './tiles'
import s from './map.module.css'

type Place = components['schemas']['MapPlace']
const route = getRouteApi('/app/map')

const count = (n: number) => (n >= 10_000 ? `${Math.round(n / 1000)}k` : n.toLocaleString('en-GB'))
const day = (d: string | null | undefined) =>
  d
    ? new Date(`${d}T12:00:00`).toLocaleDateString('en-GB', {
        day: 'numeric',
        month: 'short',
        year: 'numeric',
      })
    : ''

function tile(image: string | null | undefined, n: number, big = false): L.DivIcon {
  const size = big ? 64 : 56
  const pic = image ? ` style="background-image:url('${image}')"` : ''

  return L.divIcon({
    className: s.marker,
    html: `<div class="${s.tile}" style="width:${size}px;height:${size}px"><span class="${s.pic}"${pic}></span><span class="${s.count}">${count(n)}</span></div>`,
    iconSize: [size, size],
    iconAnchor: [size / 2, size / 2],
  })
}

type PlaceMarker = L.Marker & { place?: Place }

export function MapView() {
  const { theme } = useAppTheme()
  const box = useRef<HTMLDivElement>(null)
  const map = useRef<L.Map | null>(null)
  const search = route.useSearch()
  const navigate = useNavigate()
  const when = period(search)
  // the place picked on the map; until one is, the place the address points at
  const [picked, setPicked] = useState<string | null>(null)
  const places = useQuery({
    queryKey: ['map', when.since ?? '', when.until ?? ''],
    queryFn: async () => unwrap(await api.GET('/map', { params: { query: when } })),
  })
  const list = places.data?.places ?? []
  const pointed = search.lat != null && search.lon != null ? nearest(list, search.lat, search.lon) : null
  const chosen = picked === '' ? null : (list.find((p) => p.key === picked) ?? pointed)
  const setChosen = (p: Place | null) => setPicked(p ? p.key : '')
  const setPeriod = (next: MapSearch) =>
    void navigate({
      to: '/map',
      search: { lat: search.lat, lon: search.lon, zoom: search.zoom, ...next },
      replace: true,
    })

  useEffect(() => {
    if (!box.current || map.current) return
    map.current = L.map(box.current, { worldCopyJump: true, zoomControl: true }).setView([20, 0], 2)
    baseLayer().addTo(map.current)
    return () => {
      map.current?.remove()
      map.current = null
    }
  }, [])

  useEffect(() => {
    const m = map.current
    const all = places.data?.places
    if (!m || !all?.length) return
    const group = L.markerClusterGroup({
      showCoverageOnHover: false,
      maxClusterRadius: 70,
      iconCreateFunction: (cluster) => {
        const kids = cluster.getAllChildMarkers() as PlaceMarker[]
        const total = kids.reduce((a, k) => a + (k.place?.subs ?? 0), 0)
        const lead = kids.reduce((a, k) => ((k.place?.subs ?? 0) > (a.place?.subs ?? 0) ? k : a), kids[0])
        return tile(lead.place?.image, total, true)
      },
    })
    for (const p of all) {
      const mk = L.marker([p.lat, p.lon], {
        icon: tile(p.image, p.subs),
        title: p.targets.join(', '),
      }) as PlaceMarker
      mk.place = p
      mk.on('click', () => setPicked(p.key))
      group.addLayer(mk)
    }
    m.addLayer(group)
    return () => {
      m.removeLayer(group)
    }
  }, [places.data])

  // where to look: the place in the address, else everything shown
  const lat = search.lat
  const lon = search.lon
  const zoom = search.zoom
  useEffect(() => {
    const m = map.current
    const all = places.data?.places
    if (!m) return
    if (lat != null && lon != null) m.setView([lat, lon], zoom ?? 11)
    else if (all?.length)
      m.fitBounds(L.latLngBounds(all.map((p) => [p.lat, p.lon] as [number, number])), {
        padding: [60, 60],
        maxZoom: 9,
      })
  }, [places.data, lat, lon, zoom])

  return (
    <div className={s.page}>
      <div
        ref={box}
        className={`${s.map} ${theme === 'light' ? '' : s.darkTiles}`}
        role="region"
        aria-label="Map of where subs were shot"
      />
      <DateFilter search={search} onChange={setPeriod} />
      {places.isSuccess && !places.data.places.length && (
        <p className={s.empty}>
          {periodText(search)
            ? `No subs with a place in ${periodText(search)}.`
            : 'No subs record where they were shot yet.'}
        </p>
      )}
      {chosen && (
        <aside className={s.panel} aria-label="Place">
          <button type="button" className={s.close} aria-label="Close" onClick={() => setChosen(null)}>
            ×
          </button>
          {chosen.image && <img className={s.hero} src={chosen.image} alt="" />}
          <h2 className={s.title}>{chosen.targets.slice(0, 2).join(' · ') || 'Subs'}</h2>
          <p className="muted">
            {chosen.subs.toLocaleString('en-GB')} subs · {chosen.nights.length} night
            {chosen.nights.length === 1 ? '' : 's'}
            {chosen.first &&
              ` · ${day(chosen.first)}${chosen.last !== chosen.first ? ` to ${day(chosen.last)}` : ''}`}
          </p>
          <PlaceName lat={chosen.lat} lon={chosen.lon} />
          <h3 className="label">Shot here</h3>
          <ul className={s.nights}>
            {(chosen.collections ?? []).map((c) => (
              <li key={`${c.id}-${c.name}`}>
                {c.id != null ? (
                  // the collection's sessions, only the nights shot here
                  <Link
                    to="/collections/$id"
                    params={{ id: String(c.id) }}
                    search={{
                      tab: 'sessions',
                      nights: chosen.nights.map((n) => n.date).join(','),
                      at: `${chosen.lat.toFixed(4)},${chosen.lon.toFixed(4)}`,
                    }}
                  >
                    {c.name}
                  </Link>
                ) : (
                  <span>{c.name}</span>
                )}
                <span className="muted">{c.subs.toLocaleString('en-GB')} subs</span>
              </li>
            ))}
          </ul>
          <h3 className="label">Nights</h3>
          <ul className={s.nights}>
            {chosen.nights.map((n) => (
              <li key={n.date}>
                <Link to="/nights/$date" params={{ date: n.date }} search={{ site: n.site_key ?? undefined }}>
                  {day(n.date)}
                </Link>
                <span className="muted">{n.subs.toLocaleString('en-GB')} subs</span>
              </li>
            ))}
          </ul>
        </aside>
      )}
    </div>
  )
}

function DateFilter({ search, onChange }: { search: MapSearch; onChange: (s: MapSearch) => void }) {
  const [today] = useState(() => new Date())
  const text = periodText(search)
  const one = search.date ?? (search.from && search.from === search.to ? search.from : '')
  return (
    <div className={s.when} role="group" aria-label="Nights shown">
      <label className={s.whenDay}>
        <span className="label">Night</span>
        <input
          type="date"
          value={one}
          onChange={(e) => onChange(e.target.value ? { date: e.target.value } : {})}
        />
      </label>
      {presets(today).map((p) => (
        <button key={p.label} type="button" className={s.whenPreset} onClick={() => onChange(p.search)}>
          {p.label}
        </button>
      ))}
      <span className={s.whenText} aria-live="polite">
        {text ? `Showing ${text}` : 'Showing every night'}
      </span>
      {text && (
        <button type="button" className={s.whenPreset} onClick={() => onChange({})}>
          Every night
        </button>
      )}
    </div>
  )
}

function PlaceName({ lat, lon }: { lat: number; lon: number }) {
  const name = usePlaceName(lat, lon)
  return (
    <>
      {name.data && <p className={s.placeName}>{name.data}</p>}
      <p className={s.coords}>{coords(lat, lon)}</p>
    </>
  )
}
