// Putting things away (006-DR-40): the shared confirm, deleting a collection, the Library's Show filter, unlinking a
// finished image, and finding deletes in Activity.
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { PutAwayConfirm } from '../../components/PutAway'
import { fakeFor, json } from '../../test/fakeApi'
import { renderRoute } from '../../test/renderRoute'
import { collectionImpactLines } from '../library/CollectionMenu'

afterEach(cleanup)

const IMPACT = {
  datasets: 4,
  projects: [
    { id: 1, label: '2026', done: false, goals_set: true },
    { id: 2, label: '2025', done: true, goals_set: false },
  ],
  combined: [],
  finished: ['2026 Heart Nebula'],
  unoffered: [],
  move: null,
  location: 'active',
  libraries: [{ name: 'fast', role: 'active', files: 120, bytes: 2e9 }],
  blockers: [],
}

/** The toast saying `text` carries Undo. */
async function undoOffered(text: string | RegExp) {
  const t = await screen.findByText(text)
  expect(
    within(t.closest('[role="status"]') as HTMLElement).getByRole('button', { name: 'Undo' }),
  ).toBeInTheDocument()
}

describe('the put-away confirm', () => {
  it('always shows Files, Records, Links and goals, and Undo', () => {
    const go = vi.fn()
    render(
      <PutAwayConfirm
        verb="delete"
        name="collection Heart"
        impact={collectionImpactLines(IMPACT)}
        onConfirm={go}
        onClose={() => {}}
      />,
    )
    const dialog = screen.getByRole('dialog', { name: 'Delete collection Heart?' })
    const text = (term: string) => within(dialog).getByText(term).nextElementSibling?.textContent
    expect(text('Files')).toBe("Your files aren't touched: 120 files (2.0 GB) stay in fast.")
    expect(text('Records')).toBe(
      '4 datasets stay, as “Not in a collection”; 2 projects (2026, 2025) go with it.',
    )
    expect(text('Links and goals')).toBe(
      'Goals on 1 project go with it. No longer linked to 2026 Heart Nebula.',
    )
    expect(text('Undo')).toBe('Undo from Activity for 30 days.')
    fireEvent.click(within(dialog).getByRole('button', { name: 'Delete' }))
    expect(go).toHaveBeenCalled()
  })

  it('shows a refusal and keeps the confirm disabled', () => {
    render(
      <PutAwayConfirm
        verb="delete"
        name="collection Heart"
        impact={collectionImpactLines({ ...IMPACT, projects: [], finished: [] })}
        refused="Its files are moving to the archive. Wait for the move to finish, or cancel it."
        onConfirm={() => {}}
        onClose={() => {}}
      />,
    )
    expect(screen.getByRole('alert')).toHaveTextContent('Its files are moving to the archive.')
    expect(screen.getByRole('button', { name: 'Delete' })).toBeDisabled()
    expect(screen.getByText('No links or goals.')).toBeInTheDocument()
  })
})

describe('the collection menu', { timeout: 20_000 }, () => {
  async function openCollection(more: Record<string, unknown> = {}) {
    const r = await renderRoute('/collections/1', {
      'GET /collections/1/impact': IMPACT,
      'GET /collections/1/files': {
        ...fakeFor('get', '/collections/1/files'),
        location: 'active',
        move: null,
      },
      ...more,
    })
    const button = await screen.findByRole('button', { name: /^More for collection / })
    return { ...r, menuButton: button }
  }
  const choose = (button: HTMLElement, item: string) => {
    fireEvent.click(button)
    fireEvent.click(within(screen.getByRole('menu')).getByRole('menuitem', { name: item }))
  }

  it('offers Archive and Delete, and Edit collection only renames', async () => {
    const { menuButton } = await openCollection()
    fireEvent.click(menuButton)
    const items = within(screen.getByRole('menu'))
      .getAllByRole('menuitem')
      .map((x) => x.textContent)
    expect(items).toEqual(['Archive files…', 'Delete collection…'])
    fireEvent.keyDown(screen.getByRole('menu'), { key: 'Escape' })
    fireEvent.click(screen.getByRole('button', { name: 'Edit collection' }))
    const edit = screen.getByRole('dialog', { name: 'Edit collection' })
    expect(within(edit).queryByRole('button', { name: /Remove|Delete/ })).not.toBeInTheDocument()
  })

  it('deletes after showing what it touches, then offers Undo', async () => {
    const { api, menuButton, router } = await openCollection({
      'DELETE /collections/1': { change_id: 51, warnings: [] },
    })
    choose(menuButton, 'Delete collection…')
    const dialog = await screen.findByRole('dialog', { name: /^Delete collection / })
    expect(await within(dialog).findByText(/2 projects \(2026, 2025\) go with it/)).toBeInTheDocument()
    fireEvent.click(within(dialog).getByRole('button', { name: 'Delete collection' }))
    await waitFor(() =>
      expect(api.calls).toContainEqual({ method: 'DELETE', path: '/collections/1', body: null }),
    )
    await undoOffered(/^Deleted collection /)
    await waitFor(() => expect(router.state.location.pathname).toBe('/'))
  })

  it('is refused while files move, with the reason', async () => {
    const { menuButton } = await openCollection({
      'GET /collections/1/impact': {
        ...IMPACT,
        move: 'running',
        blockers: ['Its files are moving to the archive. Wait for the move to finish, or cancel it.'],
      },
    })
    choose(menuButton, 'Delete collection…')
    const dialog = await screen.findByRole('dialog', { name: /^Delete collection / })
    expect(await within(dialog).findByRole('alert')).toHaveTextContent('Its files are moving')
    expect(within(dialog).getByRole('button', { name: 'Delete collection' })).toBeDisabled()
  })

  it('says why when the server refuses', async () => {
    const { menuButton } = await openCollection({
      'DELETE /collections/1': json({ code: 'refused', message: 'It has combined masters.' }, 409),
    })
    choose(menuButton, 'Delete collection…')
    const dialog = await screen.findByRole('dialog', { name: /^Delete collection / })
    await within(dialog).findByText('Records')
    fireEvent.click(within(dialog).getByRole('button', { name: 'Delete collection' }))
    expect(await screen.findByText('It has combined masters.')).toBeInTheDocument()
  })
})

describe("the Library's Show filter", { timeout: 20_000 }, () => {
  function library() {
    const lib = fakeFor('GET', '/library') as { collections: Record<string, unknown>[] }
    const [a, b] = lib.collections
    lib.collections = [
      { ...a, id: 1, name: 'Heart Nebula', files_where: 'active', archive_suggested: false },
      { ...b, id: 2, name: 'Soul Nebula', files_where: 'archive', archive_suggested: false },
    ]
    return lib
  }

  it('hides fully archived collections by default, and says so', async () => {
    const { router } = await renderRoute('/', { 'GET /library': library() })
    expect(await screen.findByRole('button', { name: 'Open Heart Nebula' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Open Soul Nebula' })).not.toBeInTheDocument()
    const show = screen.getByRole('combobox', { name: 'Show' })
    expect(show).toHaveValue('current')
    expect(within(show).getByRole('option', { name: 'Archived (1)' })).toBeInTheDocument()
    expect(screen.getByText(/1 archived collection hidden/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Show' }))
    expect(await screen.findByRole('button', { name: 'Open Soul Nebula' })).toBeInTheDocument()
    expect(router.state.location.search).toMatchObject({ show: 'all' })
  })

  it('reads ?show= from the address', async () => {
    await renderRoute('/?show=archived', { 'GET /library': library() })
    expect(await screen.findByRole('button', { name: 'Open Soul Nebula' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Open Heart Nebula' })).not.toBeInTheDocument()
    expect(screen.getByRole('combobox', { name: 'Show' })).toHaveValue('archived')
    expect(screen.getAllByText('Archived').length).toBeGreaterThan(0)
  })
})

describe('your changes in Activity', { timeout: 20_000 }, () => {
  const change = (id: number, kind: string, summary: string) => ({
    id,
    kind,
    summary,
    count: 1,
    created_at: `2026-10-${String(10 + (id % 10)).padStart(2, '0')}T12:00:00Z`,
    undone_at: null,
    by: 'admin',
    can_undo: true,
  })

  it('shows 20, then More asks for the next page', async () => {
    const offsets: string[] = []
    await renderRoute('/activity', {
      'GET /changes': (_b: unknown, url: URL) => {
        const offset = Number(url.searchParams.get('offset') ?? 0)
        offsets.push(String(offset))
        const n = offset === 0 ? 20 : 3
        return Array.from({ length: n }, (_, i) =>
          change(offset + i + 1, 'agree', `Change ${offset + i + 1}`),
        )
      },
    })
    expect(await screen.findByText('Change 20')).toBeInTheDocument()
    expect(screen.queryByText('Change 21')).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'More' }))
    expect(await screen.findByText('Change 23')).toBeInTheDocument()
    expect(offsets).toContain('20')
    expect(screen.queryByRole('button', { name: 'More' })).not.toBeInTheDocument()
  })

  it('the Deleted filter lists deleted collections and projects', async () => {
    const kinds: string[] = []
    await renderRoute('/activity', {
      'GET /changes': (_b: unknown, url: URL) => {
        const kind = url.searchParams.get('kind')
        if (kind) kinds.push(kind)
        if (kind === 'collection')
          return [
            change(2, 'collection', 'Deleted collection Soul Nebula'),
            change(3, 'collection', 'Renamed X'),
          ]
        if (kind === 'project') return [change(4, 'project', 'Deleted project 2025')]
        return [change(1, 'agree', 'Agreed with 3 grades')]
      },
    })
    await screen.findByText('Agreed with 3 grades')
    fireEvent.click(screen.getByRole('radio', { name: 'Deleted' }))
    expect(await screen.findByText('Deleted collection Soul Nebula')).toBeInTheDocument()
    expect(screen.getByText('Deleted project 2025')).toBeInTheDocument()
    expect(screen.queryByText('Renamed X')).not.toBeInTheDocument()
    expect(screen.queryByText('Agreed with 3 grades')).not.toBeInTheDocument()
    expect(kinds.sort()).toEqual(['collection', 'project'])
  })
})

describe('deleting a collection, links and goals', () => {
  it('names the finished images the renderer stops being offered', () => {
    const lines = collectionImpactLines({ ...IMPACT, unoffered: ['2026 Heart Nebula'] })
    expect(lines.links).toBe(
      'Goals on 1 project go with it. No longer linked to 2026 Heart Nebula. ' +
        'No longer offered to the renderer: 2026 Heart Nebula.',
    )
    expect(
      collectionImpactLines({ ...IMPACT, projects: [], finished: [], unoffered: ['A', 'B'] }).links,
    ).toBe('No longer offered to the renderer: A, B.')
  })

  it('shows it in the confirm', async () => {
    await renderRoute('/collections/1', {
      'GET /collections/1/impact': { ...IMPACT, unoffered: ['2026 Heart Nebula'] },
    })
    fireEvent.click(await screen.findByRole('button', { name: /^More for collection / }))
    fireEvent.click(within(screen.getByRole('menu')).getByRole('menuitem', { name: 'Delete collection…' }))
    const dialog = await screen.findByRole('dialog', { name: /^Delete collection / })
    expect(
      await within(dialog).findByText(/No longer offered to the renderer: 2026 Heart Nebula\./),
    ).toBeInTheDocument()
  })
})

describe('someone who can only look', { timeout: 20_000 }, () => {
  const READ_ONLY = { ...fakeFor('GET', '/settings'), can_edit: false }
  const COMBINED = (id: number) => ({
    ...fakeFor('GET', `/collections/${id}/combined`),
    combined: [
      { ...(fakeFor('GET', `/collections/${id}/combined`).combined as object[])[0], id: 9, state: 'current' },
    ],
  })
  /** A collection with a usable master, so the Masters tab shows combined masters. */
  const usable = () => {
    const col = fakeFor('GET', '/collections/1')
    const [m] = col.masters as object[]
    return { ...col, masters: [{ ...m, state: 'current' }] }
  }
  /** A finished image linked to one project. */
  const linked = () => ({
    ...fakeFor('GET', '/finished/7'),
    id: 7,
    kind: 'astro',
    links: [{ project_id: 1, project_name: '2026', collection_id: 1, collection_name: 'Heart Nebula' }],
  })
  /** Waits for the settings to arrive, so an action that would show for an editor has had its chance. */
  async function settled(api: { calls: { method: string; path: string }[] }) {
    await waitFor(() => expect(api.calls.some((c) => c.path === '/settings')).toBe(true))
    await new Promise((r) => setTimeout(r, 50))
  }

  it('gets no collection or project menu', async () => {
    const { api } = await renderRoute('/collections/1', { 'GET /settings': READ_ONLY })
    expect(await screen.findByRole('button', { name: 'Edit collection' })).toBeInTheDocument()
    await settled(api)
    expect(screen.queryByRole('button', { name: /^More for / })).not.toBeInTheDocument()
  })

  it('an editor gets both', async () => {
    await renderRoute('/collections/1')
    expect(await screen.findByRole('button', { name: /^More for collection / })).toBeInTheDocument()
    expect(screen.getAllByRole('button', { name: /^More for (?!collection)/ }).length).toBeGreaterThan(0)
  })

  it("can't delete a stitched or stacked master", async () => {
    const { api } = await renderRoute('/collections/1?tab=masters', {
      'GET /settings': READ_ONLY,
      'GET /collections/1': usable(),
      'GET /collections/1/combined': COMBINED(1),
    })
    expect((await screen.findAllByText(/Stitched and stacked/)).length).toBeGreaterThan(0)
    await settled(api)
    expect(screen.queryByRole('button', { name: 'Delete…' })).not.toBeInTheDocument()
  })

  it('an editor can', async () => {
    await renderRoute('/collections/1?tab=masters', {
      'GET /collections/1': usable(),
      'GET /collections/1/combined': COMBINED(1),
    })
    expect((await screen.findAllByRole('button', { name: 'Delete…' })).length).toBeGreaterThan(0)
  })

  it("can't unlink a finished image", async () => {
    const { api } = await renderRoute('/finished/7', {
      'GET /settings': READ_ONLY,
      'GET /finished/7': linked(),
    })
    expect(await screen.findByText('· Read only')).toBeInTheDocument()
    await settled(api)
    expect(screen.queryByRole('button', { name: /^Unlink / })).not.toBeInTheDocument()
  })

  it('an editor can unlink', async () => {
    await renderRoute('/finished/7', { 'GET /finished/7': linked() })
    expect((await screen.findAllByRole('button', { name: /^Unlink / })).length).toBeGreaterThan(0)
  })
})
