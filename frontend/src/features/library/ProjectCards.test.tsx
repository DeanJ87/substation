import { cleanup, fireEvent, screen, waitFor, within } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'
import { renderRoute } from '../../test/renderRoute'

afterEach(cleanup)

const base = {
  name: '',
  own_name: '',
  kind_override: null,
  planned_panels: null,
  position: 0,
  dataset_ids: [11],
  panels: [],
  missing_panels: [],
  first_night: '2026-09-01',
  last_night: '2026-10-02',
  accepted_integration_s: 36000,
  goals: {},
  filter_time: { Hα: { total_s: 36000, accepted_s: 36000, rejected_s: 0 } },
  rigs: ['Askar 71F'],
  done: false,
  done_at: null,
  needs_review: false,
  review_reason: '',
  change_id: null,
  warnings: [],
}
const MOSAIC = {
  ...base,
  id: 1,
  label: '2026',
  name: '2026',
  season: '2026',
  kind: 'mosaic',
  kind_auto: 'mosaic',
  panels: [1, 2],
  planned_panels: 2,
  dataset_ids: [11, 12],
}
const WIDE = {
  ...base,
  id: 2,
  label: '2025–26 · widefield',
  name: '2025–26 · widefield',
  own_name: 'widefield',
  season: '2025–26',
  kind: 'single',
  kind_auto: 'single',
  kind_override: 'single',
  dataset_ids: [13],
}
const LIST = { projects: [MOSAIC, WIDE], unassigned: [14, 15], review: [] }
const changed = (project: object) => ({ project, change_id: 41, warnings: [] })

async function open(more: Record<string, unknown> = {}) {
  const r = await renderRoute('/collections/1', { 'GET /collections/1/projects': LIST, ...more })
  await screen.findByText('2025–26 · widefield')
  return r
}

/** The toast saying `text` carries Undo (toasts from earlier tests may still be up). */
async function undoOffered(text: string) {
  const t = await screen.findByText(text)
  expect(
    within(t.closest('[role="status"]') as HTMLElement).getByRole('button', { name: 'Undo' }),
  ).toBeInTheDocument()
}

function menu(label: string, item: string) {
  fireEvent.click(screen.getByRole('button', { name: `More for ${label}` }))
  fireEvent.click(within(screen.getByRole('menu', { name: label })).getByRole('menuitem', { name: item }))
}

describe('Projects panel (amendment 2026-10-22)', { timeout: 20_000 }, () => {
  it('shows each project by its season, with the kind and whether it was worked out', async () => {
    await open()
    const card = screen.getByText('2026').closest('article')!
    expect(within(card).getByText('Mosaic 2/2')).toBeInTheDocument()
    expect(within(card).getByText('auto')).toBeInTheDocument()
    const wide = screen.getByText('2025–26 · widefield').closest('article')!
    expect(within(wide).getByText('Single field')).toBeInTheDocument()
    expect(within(wide).queryByText('auto')).toBeNull()
  })

  it('sorts the datasets not in a project into seasons', async () => {
    const { api } = await open({
      'POST /collections/1/projects/suggest': {
        created: [],
        joined: [MOSAIC],
        placed: 2,
        change_id: 40,
        warnings: [],
      },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Sort 2 into seasons' }))
    await waitFor(() =>
      expect(api.calls).toContainEqual({
        method: 'POST',
        path: '/collections/1/projects/suggest',
        body: null,
      }),
    )
    await undoOffered('Sorted 2 datasets into seasons')
  })

  it('marks a project done from the menu and offers Undo', async () => {
    const { api } = await open({ 'PATCH /projects/2': { ...WIDE, done: true, change_id: 42 } })
    menu('2025–26 · widefield', 'Done')
    await waitFor(() =>
      expect(api.calls).toContainEqual({ method: 'PATCH', path: '/projects/2', body: { done: true } }),
    )
    await undoOffered('2025–26 · widefield marked done')
  })

  it('merges after showing what moves and which goals differ', async () => {
    const { api } = await open({
      'GET /projects/2/impact': {
        finished: [],
        combined: ['Hα v1'],
        goal_conflicts: ['Hα: goals of 10 h and 20 h'],
        datasets: 1,
      },
      'POST /collections/1/projects/merge': changed(MOSAIC),
    })
    menu('2025–26 · widefield', 'Merge into…')
    const dialog = await screen.findByRole('dialog', { name: 'Merge 2025–26 · widefield' })
    expect(await within(dialog).findByText(/Combined masters move with them: Hα v1/)).toBeInTheDocument()
    expect(within(dialog).getByText(/the larger is kept: Hα: goals of 10 h and 20 h/)).toBeInTheDocument()
    fireEvent.click(within(dialog).getByRole('button', { name: 'Merge' }))
    await waitFor(() =>
      expect(api.calls).toContainEqual({
        method: 'POST',
        path: '/collections/1/projects/merge',
        body: { into: 1, from: [2] },
      }),
    )
    await undoOffered('Merged 1 project into 2026')
  })

  it("won't merge a project linked to a finished image, and says why", async () => {
    await open({
      'GET /projects/2/impact': { finished: ['2026 Heart'], combined: [], goal_conflicts: [], datasets: 1 },
    })
    menu('2025–26 · widefield', 'Merge into…')
    const dialog = await screen.findByRole('dialog')
    expect(await within(dialog).findByText(/Linked to 2026 Heart/)).toBeInTheDocument()
    expect(within(dialog).getByRole('button', { name: 'Merge' })).toBeDisabled()
  })

  it('splits by rig', async () => {
    const two = { ...MOSAIC, rigs: ['Askar 71F', 'TTArtisan'] }
    const { api } = await open({
      'GET /collections/1/projects': { ...LIST, projects: [two, WIDE] },
      'GET /projects/1/impact': { finished: [], combined: [], goal_conflicts: [], datasets: 2 },
      'POST /projects/1/split': { ...changed(two), created: [{ ...WIDE, id: 3, label: '2026 · TTArtisan' }] },
    })
    menu('2026', 'Split…')
    const dialog = await screen.findByRole('dialog', { name: 'Split 2026' })
    fireEvent.click(within(dialog).getByRole('button', { name: 'Split' }))
    await waitFor(() =>
      expect(api.calls).toContainEqual({
        method: 'POST',
        path: '/projects/1/split',
        body: { by: 'rig', dataset_ids: [], name: '' },
      }),
    )
    expect(await screen.findByText('Split 2026: 2026 · TTArtisan')).toBeInTheDocument()
  })

  it("explains why a project with combined masters can't be deleted", async () => {
    await open({
      'GET /projects/1/impact': { finished: [], combined: ['Hα v1'], goal_conflicts: [], datasets: 2 },
    })
    menu('2026', 'Delete')
    expect(await screen.findByText(/Can't delete: it has combined masters \(Hα v1\)/)).toBeInTheDocument()
  })

  it('deletes after asking, then offers Undo', async () => {
    const { api } = await open({
      'GET /projects/2/impact': { finished: ['2026 Heart'], combined: [], goal_conflicts: [], datasets: 1 },
      'DELETE /projects/2': { change_id: 43, warnings: ['No longer linked to 2026 Heart.'] },
    })
    menu('2025–26 · widefield', 'Delete')
    fireEvent.click(await screen.findByRole('button', { name: 'Delete 2025–26 · widefield…' }))
    const ask = screen.getByRole('group', { name: 'Confirm' })
    expect(ask).toHaveTextContent('no longer linked to 2026 Heart')
    fireEvent.click(within(ask).getByRole('button', { name: 'Delete' }))
    await waitFor(() =>
      expect(api.calls).toContainEqual({ method: 'DELETE', path: '/projects/2', body: null }),
    )
    expect(await screen.findByText('Deleted 2025–26 · widefield')).toBeInTheDocument()
  })

  it('lists projects held apart for review, with Merge', async () => {
    const { api } = await open({
      'GET /collections/1/projects': {
        ...LIST,
        review: [
          { season: '2026', project_ids: [1, 2], into: 1, reasons: ['Named by hand: A, B'], mergeable: true },
        ],
      },
      'POST /collections/1/projects/merge': changed(MOSAIC),
    })
    const held = screen.getByText(/Named by hand: A, B/).closest('[role="status"]') as HTMLElement
    fireEvent.click(within(held).getByRole('button', { name: 'Merge' }))
    await waitFor(() =>
      expect(api.calls).toContainEqual({
        method: 'POST',
        path: '/collections/1/projects/merge',
        body: { into: 1, from: [2] },
      }),
    )
  })

  it('adds a project for a season with an optional name', async () => {
    const { api } = await open({
      'POST /collections/1/projects': { ...WIDE, id: 5, label: '2027 · north', change_id: 44 },
    })
    fireEvent.change(screen.getByRole('textbox', { name: 'Season' }), { target: { value: '2027' } })
    fireEvent.change(screen.getByRole('textbox', { name: 'New project name' }), {
      target: { value: 'north' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Add project' }))
    await waitFor(() =>
      expect(api.calls).toContainEqual({
        method: 'POST',
        path: '/collections/1/projects',
        body: { season: '2027', name: 'north', dataset_ids: [] },
      }),
    )
  })
})
