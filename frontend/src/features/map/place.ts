// A place's name from OpenStreetMap (Nominatim), looked up only when one is shown and kept for the session.
import { useQuery } from '@tanstack/react-query'

export function usePlaceName(lat: number | null | undefined, lon: number | null | undefined) {
  return useQuery({
    queryKey: ['place-name', lat?.toFixed(3), lon?.toFixed(3)],
    enabled: lat != null && lon != null,
    staleTime: Infinity,
    gcTime: Infinity,
    retry: false,
    queryFn: async () => {
      const r = await fetch(
        `https://nominatim.openstreetmap.org/reverse?format=jsonv2&zoom=10&accept-language=en&lat=${lat}&lon=${lon}`,
      )
      if (!r.ok) return null
      const j = (await r.json()) as { address?: Record<string, string> }
      const a = j.address ?? {}
      const local = a.city || a.town || a.village || a.municipality || a.county || a.state_district || a.state
      return [local, a.country].filter(Boolean).join(', ') || null
    },
  })
}

export const coords = (lat: number, lon: number) =>
  `${Math.abs(lat).toFixed(3)}° ${lat >= 0 ? 'N' : 'S'}, ${Math.abs(lon).toFixed(3)}° ${lon >= 0 ? 'E' : 'W'}`
