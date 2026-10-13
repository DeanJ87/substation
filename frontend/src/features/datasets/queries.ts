import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useRef } from 'react'
import { api, unwrap } from '../../api/client'
import { useLiveEvents } from '../../api/events'
import type { components } from '../../api/schema'

export type Dataset = components['schemas']['DatasetOut']
export type FrameSummary = components['schemas']['FrameSummaryOut']
export type Frame = components['schemas']['FrameOut']

export function useDatasets() {
  return useQuery({
    queryKey: ['datasets'],
    queryFn: async () => unwrap(await api.GET('/datasets', { params: { query: { limit: 1000 } } })),
  })
}

export function useDataset(id: number) {
  return useQuery({
    queryKey: ['dataset', id],
    queryFn: async () => unwrap(await api.GET('/datasets/{id}', { params: { path: { id } } })),
  })
}

export function useFrames(dataset: number) {
  return useQuery({
    queryKey: ['frames', { dataset }],
    queryFn: async () => unwrap(await api.GET('/frames', { params: { query: { dataset, limit: 1000 } } })),
  })
}

export function useFrame(sha256: string | null) {
  return useQuery({
    queryKey: ['frame', sha256],
    enabled: sha256 !== null,
    queryFn: async () => unwrap(await api.GET('/frames/{sha256}', { params: { path: { sha256: sha256! } } })),
  })
}

export function useHealth() {
  return useQuery({
    queryKey: ['health'],
    queryFn: async () => unwrap(await api.GET('/health')),
    refetchInterval: 30_000,
  })
}

/** Refetch catalogue queries when the server reports changes; batched so a burst of subs is one refetch. */
export function useCatalogueLiveUpdates() {
  const qc = useQueryClient()
  const timer = useRef<number | null>(null)
  const schedule = () => {
    if (timer.current !== null) return
    timer.current = window.setTimeout(() => {
      timer.current = null
      void qc.invalidateQueries({ queryKey: ['datasets'] })
      void qc.invalidateQueries({ queryKey: ['dataset'] })
      void qc.invalidateQueries({ queryKey: ['frames'] })
      void qc.invalidateQueries({ queryKey: ['health'] })
      void qc.invalidateQueries({ queryKey: ['frame'] })
      void qc.invalidateQueries({ queryKey: ['recon-counts'] })
      void qc.invalidateQueries({ queryKey: ['calibration-sets'] })
      void qc.invalidateQueries({ queryKey: ['masters'] })
    }, 750)
  }
  useLiveEvents({
    'frame.catalogued': schedule,
    'frame.updated': schedule,
    'dataset.updated': schedule,
    'library.status': schedule,
  })
}
