// leaflet.markercluster extends the global `L`; ES modules don't create one, so set it before the plugin loads.
import L from 'leaflet'

;(window as unknown as { L: typeof L }).L = L
