// Live updates over Server-Sent Events (contracts/events.md). EventSource resends Last-Event-ID itself
// when it reconnects; on `resync` (the server pruned our position) every cached query is refetched.
import { useQueryClient } from '@tanstack/react-query'
import { useEffect, useLayoutEffect, useRef } from 'react'

export type EventHandler = (data: unknown, type: string) => void

const TYPES = [
  'frame.catalogued',
  'frame.updated',
  'copy.moved',
  'copy.missing',
  'dataset.updated',
  'calibration.updated',
  'reconciliation.opened',
  'reconciliation.resolved',
  'queue.changed',
  'library.status',
]

export function useLiveEvents(handlers: Partial<Record<string, EventHandler>>, enabled = true) {
  const qc = useQueryClient()
  const ref = useRef(handlers)
  useLayoutEffect(() => {
    ref.current = handlers
  })

  useEffect(() => {
    if (!enabled || typeof EventSource === 'undefined') return
    const es = new EventSource('/api/v1/events', { withCredentials: true })
    const listeners = TYPES.map((type) => {
      const fn = (e: MessageEvent) => {
        let data: unknown = null
        try {
          data = JSON.parse(e.data)
        } catch {
          return
        }
        ref.current[type]?.(data, type)
        ref.current['*']?.(data, type)
      }
      es.addEventListener(type, fn)
      return [type, fn] as const
    })
    const resync = () => qc.invalidateQueries()
    es.addEventListener('resync', resync)
    return () => {
      listeners.forEach(([t, fn]) => es.removeEventListener(t, fn))
      es.removeEventListener('resync', resync)
      es.close()
    }
  }, [enabled, qc])
}
