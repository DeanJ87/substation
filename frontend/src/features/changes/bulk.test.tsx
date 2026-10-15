// Spec 016 U6: selection bars beyond subs. Calibration sets build together, calibration frames are used or left
// out together (with Undo), datasets re-grade, stack or move together (with Undo), failed jobs retry or dismiss
// together (with Undo).
import { cleanup, fireEvent, screen, waitFor, within } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'
import { fakeFor } from '../../test/fakeApi'
import { renderRoute } from '../../test/renderRoute'

afterEach(cleanup)

// the Undo button in the toast that says this
const undoIn = (text: HTMLElement) =>
  within(text.closest('[role="status"]') as HTMLElement).getByRole('button', { name: 'Undo' })

type Calls = { method: string; path: string; body: unknown }[]
const sent = async (calls: Calls, path: string) => {
  await waitFor(() => expect(calls.some((c) => c.method === 'POST' && c.path === path)).toBe(true))
  return calls.find((c) => c.method === 'POST' && c.path === path)!.body
}

describe('bulk selection (spec 016 U6)', () => {
  it('builds several calibration sets from one bar', async () => {
    const { api } = await renderRoute('/calibration', {
      'POST /bulk/calibration-sets/build': { queued: 2, skipped: [] },
    })
    const all = await screen.findByRole('checkbox', { name: /Select every set from/ })
    expect(screen.queryByRole('toolbar', { name: 'Selected calibration sets' })).toBeNull()
    fireEvent.click(all)
    const bar = screen.getByRole('toolbar', { name: 'Selected calibration sets' })
    expect(within(bar).getByText('2 sets selected')).toBeInTheDocument()
    fireEvent.click(within(bar).getByRole('button', { name: 'Build masters' }))
    expect(await sent(api.calls, '/bulk/calibration-sets/build')).toEqual({ ids: [1, 2], force: false })
    expect(await screen.findByText('Queued 2 builds')).toBeInTheDocument()
    await waitFor(() =>
      expect(screen.queryByRole('toolbar', { name: 'Selected calibration sets' })).toBeNull(),
    )
  })

  it('leaves several calibration frames out, with Undo', async () => {
    const { api } = await renderRoute('/calibration/sets/1', {
      'POST /calibration-qa/override': { queued: 2, change_id: 9 },
      'POST /changes/9/undo': {
        note: 'Put back the QA choice on 2 frames.',
        change: fakeFor('POST', '/changes/9/undo').change,
      },
    })
    const boxes = await screen.findAllByRole('checkbox', { name: /^Select / })
    fireEvent.click(boxes[0])
    const bar = screen.getByRole('toolbar', { name: 'Selected frames' })
    expect(within(bar).getByText('1 frame selected')).toBeInTheDocument()
    fireEvent.click(within(bar).getByRole('button', { name: 'Select all 2' }))
    expect(within(bar).getByText('2 frames selected')).toBeInTheDocument()
    fireEvent.click(within(bar).getByRole('button', { name: 'Leave them out' }))
    expect(await sent(api.calls, '/calibration-qa/override')).toEqual({
      sha256s: ['ab'.repeat(32), 'cd'.repeat(32)],
      verdict: 'reject',
    })
    fireEvent.click(undoIn(await screen.findByText('Leaving out 2 frames')))
    await sent(api.calls, '/changes/9/undo')
  })

  it('moves a collection’s datasets to another collection, with Undo; Escape clears', async () => {
    const col = fakeFor('GET', '/collections/1') as { datasets: { dataset: Record<string, unknown> }[] }
    col.datasets[1] = { ...col.datasets[1], dataset: { ...col.datasets[1].dataset, id: 2 } }
    const { api } = await renderRoute('/collections/1?tab=datasets', {
      'GET /collections/1': col,
      'POST /bulk/datasets/move': { moved: 2, change_id: 4 },
      'POST /changes/4/undo': {
        note: 'Put 2 datasets back where they were.',
        change: fakeFor('POST', '/changes/4/undo').change,
      },
    })
    const all = await screen.findByRole('checkbox', { name: 'Select every dataset' })
    fireEvent.click(all)
    let bar = screen.getByRole('toolbar', { name: 'Selected datasets' })
    fireEvent.keyDown(within(bar).getByRole('button', { name: 'Re-grade' }), { key: 'Escape' })
    expect(screen.queryByRole('toolbar', { name: 'Selected datasets' })).toBeNull()
    fireEvent.click(all)
    bar = screen.getByRole('toolbar', { name: 'Selected datasets' })
    const to = within(bar).getByRole('combobox', { name: 'Move to' })
    await waitFor(() => expect(within(to).getAllByRole('option').length).toBeGreaterThan(2))
    fireEvent.change(to, { target: { value: '2' } })
    fireEvent.click(within(bar).getByRole('button', { name: 'Move' }))
    expect(await sent(api.calls, '/bulk/datasets/move')).toEqual({ dataset_ids: [1, 2], collection_id: 2 })
    fireEvent.click(undoIn(await screen.findByText(/^Moved 2 datasets to /)))
    await sent(api.calls, '/changes/4/undo')
  })

  it('re-grades and stacks datasets not in a collection', async () => {
    const lib = fakeFor('GET', '/library') as { ungrouped: { dataset: Record<string, unknown> }[] }
    lib.ungrouped[1] = { ...lib.ungrouped[1], dataset: { ...lib.ungrouped[1].dataset, id: 2 } }
    const { api } = await renderRoute('/', {
      'GET /library': lib,
      'POST /bulk/datasets/regrade': { queued: 1 },
      'POST /bulk/datasets/stack': {
        started: 0,
        master_ids: [],
        skipped: [{ id: 1, reason: 'Needs at least two calibrated subs.' }],
      },
    })
    const boxes = await screen.findAllByRole('checkbox', { name: /^Select / })
    fireEvent.click(boxes[0])
    const bar = screen.getByRole('toolbar', { name: 'Selected datasets' })
    expect(within(bar).queryByRole('option', { name: 'Out of this collection' })).toBeNull()
    fireEvent.click(within(bar).getByRole('button', { name: 'Re-grade' }))
    expect(await sent(api.calls, '/bulk/datasets/regrade')).toEqual({ dataset_ids: [1] })
    expect(await screen.findByText('Re-grading 1 dataset; your own verdicts stay')).toBeInTheDocument()
    fireEvent.click((await screen.findAllByRole('checkbox', { name: /^Select / }))[1])
    const bar2 = screen.getByRole('toolbar', { name: 'Selected datasets' })
    fireEvent.click(within(bar2).getByRole('button', { name: 'Stack' }))
    fireEvent.click(within(bar2).getByRole('button', { name: 'Stack 1' }))
    expect(await sent(api.calls, '/bulk/datasets/stack')).toEqual({ dataset_ids: [2] })
    expect(await screen.findByText(/Started 0 masters · 1 skipped: Needs at least two/)).toBeInTheDocument()
  })

  it('retries and dismisses several failed jobs; dismissing offers Undo', async () => {
    const work = fakeFor('GET', '/work') as { failed: Record<string, unknown>[] }
    const failed = work.failed.map((j, i) => ({ ...j, id: `job-${i}` }))
    const { api } = await renderRoute('/activity', {
      'GET /work': { ...work, failed },
      'POST /work/bulk/jobs/retry': { done: 2, change_id: null },
      'POST /work/bulk/jobs/dismiss': { done: 2, change_id: 5 },
    })
    fireEvent.click(await screen.findByRole('checkbox', { name: 'Select all 2 failed jobs' }))
    let bar = screen.getByRole('toolbar', { name: 'Selected failed jobs' })
    expect(within(bar).getByText('2 failed jobs selected')).toBeInTheDocument()
    fireEvent.click(within(bar).getByRole('button', { name: 'Retry' }))
    expect(await sent(api.calls, '/work/bulk/jobs/retry')).toEqual({ ids: ['job-0', 'job-1'] })
    expect(await screen.findByText('Retrying 2 jobs')).toBeInTheDocument()
    // one box per kind of failure (these two differ)
    for (const box of await screen.findAllByRole('checkbox', { name: /^Select .* failed$/ }))
      fireEvent.click(box)
    bar = screen.getByRole('toolbar', { name: 'Selected failed jobs' })
    fireEvent.click(within(bar).getByRole('button', { name: 'Dismiss' }))
    expect(await sent(api.calls, '/work/bulk/jobs/dismiss')).toEqual({ ids: ['job-0', 'job-1'] })
    expect(undoIn(await screen.findByText('Dismissed 2 failed jobs'))).toBeInTheDocument()
  })
})
