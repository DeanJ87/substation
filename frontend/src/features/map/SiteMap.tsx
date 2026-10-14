// A small map of where one sub was shot (spec 012), with the place's name. Links to the full map.
import 'leaflet/dist/leaflet.css'
import { Link } from '@tanstack/react-router'
import L from 'leaflet'
import { useEffect, useRef } from 'react'
import { useAppTheme } from '../../design/ThemeContext'
import { coords, usePlaceName } from './place'
import { baseLayer } from './tiles'
import s from './map.module.css'

export function SiteMap({ lat, lon }: { lat: number; lon: number }) {
  const { theme } = useAppTheme()
  const box = useRef<HTMLDivElement>(null)
  const name = usePlaceName(lat, lon)
  useEffect(() => {
    if (!box.current) return
    const m = L.map(box.current, {
      zoomControl: false,
      attributionControl: true,
      dragging: false,
      scrollWheelZoom: false,
      doubleClickZoom: false,
      boxZoom: false,
      keyboard: false,
      touchZoom: false,
    }).setView([lat, lon], 7)
    baseLayer().addTo(m)
    L.circleMarker([lat, lon], {
      radius: 7,
      weight: 2,
      color: '#fff',
      fillOpacity: 1,
      className: s.dot,
    }).addTo(m)
    return () => {
      m.remove()
    }
  }, [lat, lon])
  return (
    <div className={s.site}>
      <div ref={box} className={`${s.mini} ${theme === 'light' ? '' : s.darkTiles}`} aria-hidden="true" />
      <p className={s.siteName}>
        <span>{name.data ?? (name.isLoading ? '…' : 'Where it was shot')}</span>
        <span className={s.coords}>{coords(lat, lon)}</span>
      </p>
      <Link to="/map" className={s.siteLink}>
        Open the map
      </Link>
    </div>
  )
}
