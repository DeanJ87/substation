// Map tiles (spec 012): OpenStreetMap's standard tiles. The dark and night-vision themes darken them through CSS
// (map.module.css), so one tile source serves every theme.
import L from 'leaflet'

export function baseLayer(): L.TileLayer {
  return L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
    maxZoom: 19,
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
  })
}
