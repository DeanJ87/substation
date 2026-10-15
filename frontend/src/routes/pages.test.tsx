// Every page mounts against data shaped like the API's and shows its content, not an error (005-DR-29).
import { cleanup, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { SHA } from '../test/fakeApi'
import { renderRoute } from '../test/renderRoute'

afterEach(() => {
  cleanup()
})

const PAGES: [string, string][] = [
  ['/', 'Library'],
  ['/collections/1', 'collection'],
  ['/collections/1?tab=datasets', 'collection datasets'],
  ['/collections/1?tab=sessions', 'collection sessions'],
  ['/collections/1?tab=masters', 'collection masters'],
  ['/datasets/1', 'dataset subs'],
  ['/datasets/1?tab=quality', 'dataset quality'],
  ['/datasets/1?tab=calibration', 'dataset calibration'],
  ['/datasets/1?tab=masters', 'dataset masters'],
  [`/datasets/1?sub=${SHA}`, 'viewer'],
  [`/subs/${SHA}`, 'sub'],
  ['/nights/2026-10-01', 'night'],
  ['/activity', 'activity'],
  ['/calibration', 'calibration'],
  ['/calibration/sets/1', 'calibration set'],
  ['/settings', 'settings'],
  ['/bin', 'bin'],
  ['/reconcile', 'reconcile'],
  ['/review', 'review'],
]

describe('pages', () => {
  it.each(PAGES)('%s (%s) renders without an error', async (url) => {
    const errors = vi.spyOn(console, 'error').mockImplementation(() => {})
    const { api } = await renderRoute(url)
    await waitFor(() => expect(api.calls.length).toBeGreaterThan(2))
    await new Promise((r) => setTimeout(r, 50))
    expect(screen.getAllByRole('navigation').length).toBeGreaterThan(0)
    expect(screen.queryByText(/something went wrong/i)).not.toBeInTheDocument()
    const thrown = errors.mock.calls.filter((c) => c.some((a) => a instanceof Error))
    expect(thrown.map((c) => String(c.find((a) => a instanceof Error)))).toEqual([])
    errors.mockRestore()
  })
})
