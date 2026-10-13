import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useRef } from 'react'
import { api, unwrap } from '../../api/client'
import { useLiveEvents } from '../../api/events'

/** Queue summary, refreshed by `queue.changed` events (at most once a second here) and a slow poll. */
export function useQueueSummary() {
  const qc = useQueryClient()
  const last = useRef(0)
  useLiveEvents({
    'queue.changed': () => {
      const now = Date.now()
      if (now - last.current < 1000) return
      last.current = now
      void qc.invalidateQueries({ queryKey: ['queue-summary'] })
    },
  })
  return useQuery({
    queryKey: ['queue-summary'],
    queryFn: async () => unwrap(await api.GET('/queue/summary')),
    refetchInterval: 15_000,
  })
}

export function etaText(seconds: number | null | undefined): string | null {
  if (seconds == null) return null
  if (seconds < 60) return 'under a minute'
  const m = Math.round(seconds / 60)
  if (m < 60) return `about ${m} min`
  const h = Math.floor(m / 60)
  return `about ${h} h ${String(m % 60).padStart(2, '0')} min`
}
