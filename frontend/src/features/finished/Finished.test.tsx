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
  processing: ['GraXpert', 'BlurXTerminator'],
  files: [
    file(1, 'exports/heart-final.png'),
    file(2, 'exports/heart-starless.png', { role: 'starless', key: 'starless' }),
    file(3, 'exports/heart-ha.tif'),
    file(4, 'project/heart.xisf', { servable: false }),
  ],
  changed_at: '2026-10-20T21:30:00Z',
  can_write_project_json: false,
  project_json_reason: 'Mounted read-only. Mount it read-write (SUBSTATION_LIBRARY_4_MODE=rw) to allow this.',
}

const LIST = {
  projects: [PROJECT],
  libraries: ['completed'],
  not_projects: [['Astro/stray', 'no exports, web, social or project folder']],
}
const ADMIN = { ...fakeFor('GET', '/settings'), can_edit: true }

describe('Finished (spec 020)', () => {
  it('lists each project with its status, links, roles, processing and changed time', async () => {
    await renderRoute('/finished', { 'GET /finished': LIST })
    const row = (await screen.findByRole('link', { name: '2026 Heart Nebula' })).closest('tr')!
    expect(row).toHaveTextContent('Astro · IC 1805')
    expect(row).toHaveTextContent('Not offered: needs a final image')
    expect(within(row).getByRole('link', { name: 'Heart Nebula' })).toHaveAttribute('href', '/collections/4')
    expect(row).toHaveTextContent('4 files')
    expect(row).toHaveTextContent('Starless: heart-starless.png')
    expect(row).toHaveTextContent('GraXpert → BlurXTerminator')
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
    'PUT /finished/7/processing': PROJECT,
    'POST /finished/7/roles/guess': PROJECT,
    ...overrides,
  })
  await screen.findByRole('heading', { name: '2026 Heart Nebula' })
  return r
}

describe('a finished project (spec 020)', () => {
  it('says why it is not offered to the renderer', async () => {
    await openProject()
    expect(screen.getByText(/^Not offered to the renderer yet/)).toHaveTextContent(
      'Not offered to the renderer yet: needs a final image.',
    )
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
            { file_id: 1, role: 'starless', role_filter: '', role_order: null },
            { file_id: 2, role: '', role_filter: '', role_order: null },
            { file_id: 3, role: 'per_filter', role_filter: 'Hα', role_order: null },
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
        body: { roles: [{ file_id: 3, role: 'progressive', role_filter: '', role_order: 2 }] },
      }),
    )
    fireEvent.click(screen.getByRole('button', { name: 'Guess again from file names' }))
    await waitFor(() =>
      expect(api.calls.some((c) => c.method === 'POST' && c.path === '/finished/7/roles/guess')).toBe(true),
    )
  })

  it('lists working files greyed, without a role', async () => {
    await openProject()
    const row = screen.getByText('project/heart.xisf').closest('tr')!
    expect(row).toHaveTextContent('Not offered to the renderer')
    expect(within(row).queryByRole('combobox')).not.toBeInTheDocument()
  })

  it('edits the processing steps in order', async () => {
    const { api } = await openProject()
    fireEvent.click(screen.getByRole('button', { name: 'Move step 2 up' }))
    fireEvent.change(screen.getByRole('textbox', { name: 'New step' }), {
      target: { value: 'StarXTerminator' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Add step' }))
    fireEvent.click(screen.getByRole('button', { name: 'Save steps' }))
    await waitFor(() =>
      expect(api.calls).toContainEqual({
        method: 'PUT',
        path: '/finished/7/processing',
        body: { steps: ['BlurXTerminator', 'GraXpert', 'StarXTerminator'] },
      }),
    )
  })

  it('keeps Write project.json disabled with the reason on a read-only library', async () => {
    await openProject()
    const write = screen.getByRole('button', { name: 'Write project.json' })
    expect(write).toBeDisabled()
    expect(write).toHaveAccessibleDescription(PROJECT.project_json_reason)
  })

  it('shows why the server refused to write project.json', async () => {
    await renderRoute('/finished/7', {
      'GET /settings': ADMIN,
      'GET /finished/7': { ...PROJECT, can_write_project_json: true, project_json_reason: '' },
    })
    // the fake API only answers 2xx: this one call is refused as the server would
    const fetch = (globalThis as { testFetch?: typeof globalThis.fetch }).testFetch!
    ;(globalThis as { testFetch?: typeof globalThis.fetch }).testFetch = (async (
      input: RequestInfo | URL,
      init?: RequestInit,
    ) => {
      const req = input instanceof Request ? input : new Request(String(input), init)
      if (req.method === 'POST' && req.url.endsWith('/finished/7/project-json'))
        return new Response(
          JSON.stringify({
            code: 'not_ours',
            message: "There's a project.json here that SubStation didn't write; it won't overwrite it.",
          }),
          { status: 409, headers: { 'Content-Type': 'application/json' } },
        )
      return fetch(input, init)
    }) as typeof globalThis.fetch
    fireEvent.click(await screen.findByRole('button', { name: 'Write project.json' }))
    expect(await screen.findByRole('alert')).toHaveTextContent("didn't write; it won't overwrite it.")
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
    expect(await screen.findByText('Only an admin can change finished projects.')).toBeInTheDocument()
    expect(screen.getByRole('combobox', { name: 'Role of exports/heart-final.png' })).toBeDisabled()
    expect(screen.queryByRole('button', { name: 'Guess again from file names' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /^Link / })).not.toBeInTheDocument()
  })
})
