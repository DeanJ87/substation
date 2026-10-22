import { cleanup, fireEvent, screen, waitFor, within } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'
import { fakeFor } from '../../test/fakeApi'
import { renderRoute } from '../../test/renderRoute'
import type { Finished } from './queries'

afterEach(cleanup)

const file = (id: number, rel_path: string, more: Partial<Finished['files'][number]> = {}) => ({
  id,
  rel_path,
  section: rel_path.split('/')[0],
  size_bytes: 12_400_000,
  missing: false,
  servable: true,
  role: '',
  role_filter: '',
  role_order: null,
  role_label: '',
  key: null,
  ...more,
})

const PROJECT: Finished = {
  id: 7,
  library: 'completed',
  rel_path: 'Astro/IC 1805/2026 Heart Nebula',
  kind: 'astro',
  subject: 'IC 1805',
  name: '2026 Heart Nebula',
  missing: false,
  offered: false,
  reason: 'needs a final image',
  links: [{ project_id: 3, project_name: 'Heart Nebula', collection_id: 4, collection_name: 'Heart Nebula' }],
  path: '/data/completed/Astro/IC 1805/2026 Heart Nebula',
  distance_ly: null,
  distance_source: '',
  files: [
    file(1, 'exports/heart-final.png'),
    file(2, 'exports/heart-starless.png', { role: 'starless', key: 'starless' }),
    file(3, 'exports/heart-ha.tif'),
    file(5, 'web/heart-step1.jpg', { role: 'step', role_order: 1, role_label: 'Master' }),
    file(4, 'project/heart.xisf', { servable: false }),
  ],
  changed_at: '2026-10-20T21:30:00Z',
}

const LIST = {
  projects: [PROJECT],
  libraries: ['completed'],
  not_projects: [['Astro/stray', 'no exports, web, social or project folder']],
}
const ADMIN = { ...fakeFor('GET', '/settings'), can_edit: true }

describe('Finished (spec 020)', () => {
  it('lists each project with its final image, links and status', async () => {
    const final = { ...PROJECT, files: [file(1, 'exports/heart-final.png', { role: 'final' })] }
    await renderRoute('/finished', { 'GET /finished': { ...LIST, projects: [final] } })
    const row = (await screen.findByRole('link', { name: '2026 Heart Nebula' })).closest('li')!
    expect(row).toHaveTextContent('Astro · IC 1805')
    expect(row).toHaveTextContent('Not offered')
    expect(within(row).getByRole('button', { name: 'Help: Why not offered' })).toBeInTheDocument()
    expect(within(row).getByRole('link', { name: 'Heart Nebula' })).toHaveAttribute('href', '/collections/4')
    expect(row.querySelector('img')).toHaveAttribute('src', '/api/v1/finished/7/files/1/image?size=thumb')
    expect(row).not.toHaveTextContent('heart-final.png')
    expect(screen.getByRole('link', { name: 'Finished' })).toBeInTheDocument()
  })

  it('lists folders that are not projects, with the reason', async () => {
    await renderRoute('/finished', { 'GET /finished': LIST })
    fireEvent.click(await screen.findByRole('button', { name: /Not a project/ }))
    expect(screen.getByText('Astro/stray')).toBeInTheDocument()
    expect(screen.getByText(/no exports, web, social or project folder/)).toBeInTheDocument()
  })

  it('explains the Completed library and the folder layout when there is none', async () => {
    await renderRoute('/finished', { 'GET /finished': { projects: [], libraries: [], not_projects: [] } })
    expect(await screen.findByRole('heading', { name: 'No Completed library yet' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Settings → Library' })).toBeInTheDocument()
    expect(screen.getByText('completed')).toBeInTheDocument()
    expect(screen.getByLabelText('Folder layout')).toHaveTextContent(
      '<Astro | Nightscapes | Videos>/<subject>/<name>/',
    )
    expect(screen.queryByRole('button', { name: 'Rescan' })).not.toBeInTheDocument()
  })

  it('says when the library has no projects yet, and rescans on request', async () => {
    const { api } = await renderRoute('/finished', {
      'GET /finished': { projects: [], libraries: ['completed'], not_projects: [] },
    })
    expect(await screen.findByRole('heading', { name: 'No finished projects yet' })).toBeInTheDocument()
    expect(screen.getByLabelText('Folder layout')).toHaveTextContent('exports/')
    fireEvent.click(screen.getByRole('button', { name: 'Rescan' }))
    await waitFor(() =>
      expect(api.fetch.mock.calls.some(([r]) => String((r as Request).url).includes('rescan=true'))).toBe(
        true,
      ),
    )
  })
})

async function openProject(overrides: Record<string, unknown> = {}) {
  const r = await renderRoute('/finished/7', {
    'GET /settings': ADMIN,
    'GET /finished/7': PROJECT,
    'GET /finished/7/suggestions': [
      {
        project_id: 9,
        project_name: 'Heart Nebula 2025',
        collection_id: 5,
        collection_name: 'Heart Nebula (old)',
        score: 2.5,
        reasons: ['same target (IC1805)', 'same year'],
      },
    ],
    'PUT /finished/7/roles': PROJECT,
    'PUT /finished/7/links': PROJECT,
    'PUT /finished/7/distance': (b: unknown) => ({
      ...PROJECT,
      distance_ly: (b as { distance_ly: number | null }).distance_ly,
      distance_source: 'manual',
    }),
    'POST /finished/7/roles/guess': PROJECT,
    ...overrides,
  })
  await screen.findByRole('heading', { name: '2026 Heart Nebula' })
  return r
}

describe('a finished project (spec 020)', () => {
  it('says why it is not offered to the renderer behind a help button', async () => {
    await openProject()
    expect(screen.getByText('Not offered')).toBeInTheDocument()
    const help = screen.getByRole('button', { name: 'Help: Why not offered' })
    expect(screen.queryByRole('tooltip')).not.toBeInTheDocument()
    fireEvent.click(help)
    expect(screen.getByRole('tooltip')).toHaveTextContent('needs a final image')
    expect(help).toHaveAccessibleDescription('needs a final image')
    fireEvent.keyDown(help, { key: 'Escape' })
    expect(screen.queryByRole('tooltip')).not.toBeInTheDocument()
  })

  it('links a suggested project, with the reasons shown', async () => {
    const { api } = await openProject()
    expect(await screen.findByText(/same target \(IC1805\), same year/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Link Heart Nebula 2025' }))
    await waitFor(() =>
      expect(api.calls).toContainEqual({
        method: 'PUT',
        path: '/finished/7/links',
        body: { project_ids: [3, 9] },
      }),
    )
  })

  it('sends only the changed file roles, taking a single role from the file that had it', async () => {
    const { api } = await openProject()
    fireEvent.change(screen.getByRole('combobox', { name: 'Role of exports/heart-final.png' }), {
      target: { value: 'final' },
    })
    fireEvent.change(screen.getByRole('combobox', { name: 'Role of exports/heart-ha.tif' }), {
      target: { value: 'per_filter' },
    })
    const save = screen.getByRole('button', { name: 'Save roles' })
    expect(save).toBeDisabled() // a single filter needs its filter
    expect(screen.getByText('A single-filter image needs its filter.')).toBeInTheDocument()
    fireEvent.change(screen.getByRole('textbox', { name: 'Filter of exports/heart-ha.tif' }), {
      target: { value: 'Hα' },
    })
    // the starless file becomes the final: the old starless file loses its role
    fireEvent.change(screen.getByRole('combobox', { name: 'Role of exports/heart-final.png' }), {
      target: { value: 'starless' },
    })
    fireEvent.click(save)
    await waitFor(() =>
      expect(api.calls).toContainEqual({
        method: 'PUT',
        path: '/finished/7/roles',
        body: {
          roles: [
            { file_id: 1, role: 'starless', role_filter: '', role_order: null, role_label: '' },
            { file_id: 2, role: '', role_filter: '', role_order: null, role_label: '' },
            { file_id: 3, role: 'per_filter', role_filter: 'Hα', role_order: null, role_label: '' },
          ],
        },
      }),
    )
  })

  it('gives a progressive stack its position, and guesses again on request', async () => {
    const { api } = await openProject()
    fireEvent.change(screen.getByRole('combobox', { name: 'Role of exports/heart-ha.tif' }), {
      target: { value: 'progressive' },
    })
    fireEvent.change(screen.getByRole('spinbutton', { name: 'Order of exports/heart-ha.tif' }), {
      target: { value: '2' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Save roles' }))
    await waitFor(() =>
      expect(api.calls).toContainEqual({
        method: 'PUT',
        path: '/finished/7/roles',
        body: {
          roles: [{ file_id: 3, role: 'progressive', role_filter: '', role_order: 2, role_label: '' }],
        },
      }),
    )
    fireEvent.click(screen.getByRole('button', { name: 'Guess again' }))
    await waitFor(() =>
      expect(api.calls.some((c) => c.method === 'POST' && c.path === '/finished/7/roles/guess')).toBe(true),
    )
  })

  it('shows images as cards with a preview, and working files in a folded list without a role', async () => {
    await openProject()
    expect(screen.queryByRole('combobox', { name: 'Role of project/heart.xisf' })).not.toBeInTheDocument()
    expect(screen.getByText('Working files')).toBeInTheDocument()
    expect(screen.getByText('project/heart.xisf')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Preview exports/heart-ha.tif' }))
    const dialog = screen.getByRole('dialog', { name: 'heart-ha.tif' })
    expect(within(dialog).getByRole('img')).toHaveAttribute(
      'src',
      '/api/v1/finished/7/files/3/image?size=preview',
    )
  })

  it('gives a processing step its position and label, and shows the steps in order', async () => {
    const { api } = await openProject()
    const section = screen.getByRole('heading', { name: /Processing steps/ }).closest('section')!
    expect(section).toHaveTextContent('1 · Master')
    fireEvent.change(screen.getByRole('combobox', { name: 'Role of exports/heart-ha.tif' }), {
      target: { value: 'step' },
    })
    expect(screen.getByRole('spinbutton', { name: 'Order of exports/heart-ha.tif' })).toHaveValue(2)
    expect(screen.getByRole('button', { name: 'Save roles' })).toBeDisabled()
    expect(screen.getByText('A processing step needs a label.')).toBeInTheDocument()
    fireEvent.change(screen.getByRole('textbox', { name: 'Step label of exports/heart-ha.tif' }), {
      target: { value: 'GraXpert + NoiseXTerminator' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Save roles' }))
    await waitFor(() =>
      expect(api.calls).toContainEqual({
        method: 'PUT',
        path: '/finished/7/roles',
        body: {
          roles: [
            {
              file_id: 3,
              role: 'step',
              role_filter: '',
              role_order: 2,
              role_label: 'GraXpert + NoiseXTerminator',
            },
          ],
        },
      }),
    )
  })

  it('saves a distance typed in, and clears it', async () => {
    const { api } = await openProject()
    const input = screen.getByRole('textbox', { name: 'Distance in light years' })
    fireEvent.change(input, { target: { value: '7,500' } })
    fireEvent.blur(input)
    await waitFor(() =>
      expect(api.calls).toContainEqual({
        method: 'PUT',
        path: '/finished/7/distance',
        body: { distance_ly: 7500 },
      }),
    )
    expect(await screen.findByText('Set by hand')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Look up' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Look up' })).toHaveAccessibleDescription(
      'Clear it to look it up.',
    )
    fireEvent.click(screen.getByRole('button', { name: 'Clear' }))
    await waitFor(() =>
      expect(api.calls).toContainEqual({
        method: 'PUT',
        path: '/finished/7/distance',
        body: { distance_ly: null },
      }),
    )
  })

  it("shows the server's reason when a distance can't be looked up", async () => {
    await openProject()
    const fetch = (globalThis as { testFetch?: typeof globalThis.fetch }).testFetch!
    ;(globalThis as { testFetch?: typeof globalThis.fetch }).testFetch = (async (
      input: RequestInfo | URL,
      init?: RequestInit,
    ) => {
      const req = input instanceof Request ? input : new Request(String(input), init)
      if (req.method === 'POST' && req.url.endsWith('/finished/7/distance/lookup'))
        return new Response(
          JSON.stringify({ code: 'not_found', message: 'SIMBAD has no distance for IC 1805.' }),
          { status: 404, headers: { 'Content-Type': 'application/json' } },
        )
      return fetch(input, init)
    }) as typeof globalThis.fetch
    fireEvent.click(screen.getByRole('button', { name: 'Look up' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('SIMBAD has no distance for IC 1805.')
  })

  it('previews the render data when opened', async () => {
    await openProject({ 'GET /finished/7/render-data': { schema_version: 1, project: { id: '7' } } })
    fireEvent.click(screen.getByRole('button', { name: 'Preview render data' }))
    expect(await screen.findByRole('textbox', { name: 'Render data' })).toHaveValue(
      JSON.stringify({ schema_version: 1, project: { id: '7' } }, null, 2),
    )
  })

  it('shows changes as read-only to someone who is not an admin', async () => {
    await openProject({ 'GET /settings': { ...ADMIN, can_edit: false } })
    expect(await screen.findByText('· Read only')).toBeInTheDocument()
    expect(screen.getByRole('combobox', { name: 'Role of exports/heart-final.png' })).toBeDisabled()
    expect(screen.queryByRole('button', { name: 'Guess again' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /^Link / })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Look up' })).not.toBeInTheDocument()
    expect(screen.getByRole('textbox', { name: 'Distance in light years' })).toBeDisabled()
  })
})

const checkpoint = (order: number, label: string, integration_s: number, subs: number) => ({
  order,
  nights: [],
  label,
  integration_s,
  subs,
  filters: {},
  image_url: `/api/v1/finished/7/progression/${order}/image`,
})
const progression = (more: Record<string, unknown> = {}) => ({
  state: 'none',
  step: '',
  progress: 0,
  reason: '',
  mapping: '',
  built_at: null,
  checkpoints: [],
  ...more,
})
const BUILT = progression({
  state: 'done',
  mapping: 'HOO',
  built_at: '2026-10-21T08:00:00Z',
  // out of order on purpose: the page shows them by order
  checkpoints: [
    checkpoint(2, '3–4 Oct', 16_200, 54),
    checkpoint(1, '2 Oct', 7_200, 24),
    checkpoint(3, '9 Oct', 25_200, 84),
  ],
})
const progressionSection = async () =>
  (await screen.findByRole('heading', { name: /Progression/ })).closest('section')!

describe('the progression of a finished project (020-DR-15)', () => {
  it('offers Generate before anything is built, and posts it', async () => {
    const { api } = await openProject({
      'GET /finished/7/progression': progression(),
      'POST /finished/7/progression': progression({ state: 'queued', step: 'Waiting for a worker' }),
    })
    const section = await progressionSection()
    fireEvent.click(await within(section).findByRole('button', { name: 'Generate' }))
    await waitFor(() =>
      expect(api.calls).toContainEqual({
        method: 'POST',
        path: '/finished/7/progression',
        body: { force: false },
      }),
    )
    expect(await within(section).findByRole('progressbar')).toBeInTheDocument()
    expect(within(section).queryByRole('button', { name: 'Generate' })).not.toBeInTheDocument()
  })

  it('shows the step and a progress bar while building', async () => {
    await openProject({
      'GET /finished/7/progression': progression({
        state: 'running',
        step: 'Stack 2 Oct Hα',
        progress: 0.42,
      }),
    })
    const section = await progressionSection()
    expect(await within(section).findByRole('progressbar')).toHaveAttribute('aria-valuenow', '0.42')
    expect(section).toHaveTextContent('Building · Stack 2 Oct Hα')
    expect(section).toHaveTextContent('42%')
    expect(within(section).queryByRole('button', { name: /Generate|Rebuild/ })).not.toBeInTheDocument()
  })

  it("says why it can't be built, with no button", async () => {
    await openProject({
      'GET /finished/7/progression': progression({ state: 'unavailable', reason: 'This is a mosaic.' }),
    })
    const section = await progressionSection()
    expect(await within(section).findByText('This is a mosaic.')).toBeInTheDocument()
    expect(within(section).queryByRole('button', { name: /Generate|Rebuild/ })).not.toBeInTheDocument()
  })

  it('shows the stacks in order, labelled, and rebuilds with force', async () => {
    const { api } = await openProject({
      'GET /finished/7/progression': BUILT,
      'POST /finished/7/progression': BUILT,
    })
    const section = await progressionSection()
    const strip = await within(section).findByRole('list', { name: 'Stacks after each night' })
    const items = within(strip).getAllByRole('listitem')
    expect(items.map((li) => li.textContent)).toEqual([
      '2 Oct · 2h · 24 subs',
      '3–4 Oct · 4h 30m · 54 subs',
      '9 Oct · 7h · 84 subs',
    ])
    expect(items[0].querySelector('img')).toHaveAttribute('src', '/api/v1/finished/7/progression/1/image')
    fireEvent.click(within(section).getByRole('button', { name: 'Rebuild' }))
    await waitFor(() =>
      expect(api.calls).toContainEqual({
        method: 'POST',
        path: '/finished/7/progression',
        body: { force: true },
      }),
    )
  })

  it("shows the server's refusal beside the button", async () => {
    await openProject({ 'GET /finished/7/progression': progression() })
    const g = globalThis as { testFetch?: typeof globalThis.fetch }
    const fetch = g.testFetch!
    g.testFetch = (async (input: RequestInfo | URL, init?: RequestInit) => {
      const req = input instanceof Request ? input : new Request(String(input), init)
      if (req.method === 'POST' && req.url.endsWith('/finished/7/progression'))
        return new Response(
          JSON.stringify({ code: 'unavailable', message: 'Needs at least two kept subs.' }),
          {
            status: 409,
            headers: { 'Content-Type': 'application/json' },
          },
        )
      return fetch(input, init)
    }) as typeof globalThis.fetch
    const section = await progressionSection()
    fireEvent.click(await within(section).findByRole('button', { name: 'Generate' }))
    expect(await within(section).findByRole('alert')).toHaveTextContent('Needs at least two kept subs.')
  })

  it('opens a stack larger and steps through them in order with Prev, Next and the arrow keys', async () => {
    await openProject({ 'GET /finished/7/progression': BUILT })
    const section = await progressionSection()
    fireEvent.click(await within(section).findByRole('button', { name: 'Open 3–4 Oct' }))
    let dialog = screen.getByRole('dialog', { name: 'Progression: 3–4 Oct' })
    expect(within(dialog).getByRole('img')).toHaveAttribute('src', '/api/v1/finished/7/progression/2/image')
    expect(dialog).toHaveTextContent('2 of 3')
    fireEvent.click(within(dialog).getByRole('button', { name: /Next/ }))
    dialog = screen.getByRole('dialog', { name: 'Progression: 9 Oct' })
    expect(within(dialog).getByRole('button', { name: /Next/ })).toBeDisabled()
    fireEvent.keyDown(dialog, { key: 'ArrowLeft' })
    fireEvent.keyDown(dialog, { key: 'ArrowLeft' })
    dialog = screen.getByRole('dialog', { name: 'Progression: 2 Oct' })
    expect(within(dialog).getByRole('button', { name: /Prev/ })).toBeDisabled()
    fireEvent.click(within(dialog).getByRole('button', { name: /Next/ }))
    expect(screen.getByRole('dialog', { name: 'Progression: 3–4 Oct' })).toBeInTheDocument()
  })

  it('is not shown until the project is linked', async () => {
    await openProject({ 'GET /finished/7': { ...PROJECT, links: [] } })
    expect(screen.queryByRole('heading', { name: /Progression/ })).not.toBeInTheDocument()
  })
})
