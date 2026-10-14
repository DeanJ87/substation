// The map (spec 012): every place subs were shot, as a picture with a count that merges with its neighbours as you
// zoom out, like a phone's photo map. Choosing a place lists its nights; a night opens the night page.
import 'leaflet/dist/leaflet.css'
import { useQuery } from '@tanstack/react-query'
import { Link } from '@tanstack/react-router'
import L from 'leaflet'
import './leafletGlobal'
import 'leaflet.markercluster'
import { useEffect, useRef, useState } from 'react'
import { api, unwrap } from '../../api/client'
import type { components } from '../../api/schema'
import { useAppTheme } from '../../design/ThemeContext'
import { coords, usePlaceName } from './place'
import { baseLayer } from './tiles'
import s from './map.module.css'

type Place = components['schemas']['MapPlace']

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
  const [chosen, setChosen] = useState<Place | null>(null)
  const places = useQuery({ queryKey: ['map'], queryFn: async () => unwrap(await api.GET('/map')) })

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
    const list = places.data?.places
    if (!m || !list?.length) return
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
    for (const p of list) {
      const mk = L.marker([p.lat, p.lon], {
        icon: tile(p.image, p.subs),
        title: p.targets.join(', '),
      }) as PlaceMarker
      mk.place = p
      mk.on('click', () => setChosen(p))
      group.addLayer(mk)
    }
    m.addLayer(group)
    m.fitBounds(group.getBounds(), { padding: [60, 60], maxZoom: 9 })
    return () => {
      m.removeLayer(group)
    }
  }, [places.data])

  return (
    <div className={s.page}>
      <div
        ref={box}
        className={`${s.map} ${theme === 'light' ? '' : s.darkTiles}`}
        role="region"
        aria-label="Map of where subs were shot"
      />
      {places.isSuccess && !places.data.places.length && (
        <p className={s.empty}>No subs record where they were shot yet.</p>
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
          {chosen.targets.length > 2 && <p className="muted">Also {chosen.targets.slice(2).join(', ')}</p>}
          <h3 className="label">Nights</h3>
          <ul className={s.nights}>
            {chosen.nights.map((n) => (
              <li key={n.date}>
                <Link to="/nights/$date" params={{ date: n.date }}>
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

function PlaceName({ lat, lon }: { lat: number; lon: number }) {
  const name = usePlaceName(lat, lon)
  return (
    <>
      {name.data && <p className={s.placeName}>{name.data}</p>}
      <p className={s.coords}>{coords(lat, lon)}</p>
    </>
  )
}
