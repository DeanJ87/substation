import { cleanup, fireEvent, screen, waitFor, within } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'
import { fakeFor } from '../../test/fakeApi'
import { renderRoute } from '../../test/renderRoute'
import { byShow } from './Library'
import { whereText } from './CollectionFiles'

afterEach(cleanup)

const LIBS = [
  { id: 1, name: 'fast', role: 'active', files: 120, bytes: 6_000_000_000 },
  { id: 2, name: 'big', role: 'archive', files: 0, bytes: 0 },
]
const FILES = {
  location: 'active',
  libraries: [LIBS[0]],
  active_bytes: 6_000_000_000,
  archive_bytes: 0,
  move: null,
  archive: { possible: true, reason: null, from_library: 'fast', to_library: 'big' },
  bring_back: { possible: false, reason: 'None of its files are in an archive library.' },
  suggested: true,
  suggest_after_days: 60,
  can_move: true,
}
const PREVIEW = {
  direction: 'archive',
  from_library: 'fast',
  to_library: 'big',
  files: 122,
  bytes: 6_100_000_000,
  lights: 120,
  calibration: 2,
  calibration_kept: 1,
}

async function open(files: object = FILES) {
  const r = await renderRoute('/collections/1', {
    'GET /collections/1/files': files,
    'GET /collections/1/move-preview': PREVIEW,
    'POST /collections/1/move': {
      ...fakeFor('POST', '/collections/1/move'),
      state: 'queued',
      files_total: 122,
      to_library: 'big',
      change_id: 7,
    },
  })
  await screen.findByRole('heading', { name: 'Files' })
  return r
}

describe('Collection → Files (spec 013)', () => {
  it('says where the files are and that it is worth archiving', async () => {
    await open()
    expect(screen.getByText('Active · 120 files · 6.0 GB in fast')).toBeInTheDocument()
    expect(screen.getByText(/Worth archiving: no new subs for over 60 days/)).toBeInTheDocument()
  })

  it('asks first, showing the files, the space and both libraries, then queues the move', async () => {
    const { api } = await open()
    fireEvent.click(screen.getByRole('button', { name: 'Archive…' }))
    const ask = await screen.findByRole('group', { name: /^Archive/ })
    await within(ask).findByText(/move 122 files \(6\.1 GB\) from/)
    expect(within(ask).getByText('fast')).toBeInTheDocument()
    expect(within(ask).getByText('big')).toBeInTheDocument()
    expect(ask).toHaveTextContent('1 calibration frame that other collections in fast still use stays there')
    fireEvent.click(within(ask).getByRole('button', { name: 'Archive 122 files' }))
    await waitFor(() =>
      expect(api.calls).toContainEqual({
        method: 'POST',
        path: '/collections/1/move',
        body: { direction: 'archive' },
      }),
    )
  })

  it('cancelling the question moves nothing', async () => {
    const { api } = await open()
    fireEvent.click(screen.getByRole('button', { name: 'Archive…' }))
    const ask = await screen.findByRole('group', { name: /^Archive/ })
    fireEvent.click(within(ask).getByRole('button', { name: 'Cancel' }))
    expect(screen.getByRole('button', { name: 'Archive…' })).toBeInTheDocument()
    expect(api.calls.some((c) => c.method === 'POST' && c.path === '/collections/1/move')).toBe(false)
  })

  it('keeps Archive in view, disabled, with the reason when a library is read-only', async () => {
    const why = 'big: Mounted read-only. Mount it read-write (SUBSTATION_LIBRARY_2_MODE=rw) to allow this.'
    await open({ ...FILES, suggested: false, archive: { possible: false, reason: why } })
    const button = screen.getByRole('button', { name: 'Archive…' })
    expect(button).toBeDisabled()
    expect(button).toHaveAccessibleDescription(why)
  })

  it('offers Bring back for an archived collection, and says why a read-only account cannot', async () => {
    await open({
      ...FILES,
      location: 'archive',
      libraries: [{ ...LIBS[1], files: 120, bytes: 6_000_000_000 }],
      bring_back: { possible: true, from_library: 'big', to_library: 'fast' },
      can_move: false,
    })
    expect(screen.queryByRole('button', { name: 'Archive…' })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Bring back…' })).toHaveAccessibleDescription(
      "Read-only accounts can't move files.",
    )
  })

  it('follows a move under way and cancels it', async () => {
    const { api } = await open({
      ...FILES,
      suggested: false,
      move: {
        ...fakeFor('POST', '/moves/5/cancel'),
        id: 5,
        direction: 'archive',
        state: 'running',
        from_library: 'fast',
        to_library: 'big',
        files_done: 40,
        files_total: 122,
        bytes_done: 2_000_000_000,
        bytes_total: 6_100_000_000,
        problems: 1,
        problem_files: [{ path: 'M 31/Light_1.fits', reason: 'A different file is already there.' }],
      },
    })
    expect(
      screen.getByText(/Archiving: fast → big · 40 of 122 files · 2\.0 GB of 6\.1 GB/),
    ).toBeInTheDocument()
    expect(screen.getByRole('progressbar', { name: 'Files moved' })).toHaveAttribute('aria-valuenow', '33')
    expect(screen.getByText('1 file left where it was')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Archive…' })).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Cancel move' }))
    await waitFor(() => expect(api.calls.some((c) => c.path === '/moves/5/cancel')).toBe(true))
  })

  it('dismisses the suggestion', async () => {
    const { api } = await open()
    fireEvent.click(screen.getByRole('button', { name: 'Not now' }))
    await waitFor(() =>
      expect(api.calls.some((c) => c.path === '/collections/1/archive-suggestion/dismiss')).toBe(true),
    )
  })
})

describe('where a collection is', () => {
  it('reads as a sentence', () => {
    expect(whereText({ location: 'both', libraries: LIBS.map((l) => ({ ...l, bytes: 1e9 })) })).toBe(
      'Partly archived · 1.0 GB in fast (active), 1.0 GB in big (archive)',
    )
    expect(whereText({ location: 'archive', libraries: [{ ...LIBS[1], files: 16, bytes: 5e6 }] })).toBe(
      'Archived · 16 files · 5.0 MB in big',
    )
    expect(whereText({ location: '', libraries: [] })).toBe('No files on disk')
  })
  it('filters the Library', () => {
    const cards = [
      { id: 1, files_where: 'active', archive_suggested: true },
      { id: 2, files_where: 'archive', archive_suggested: false },
    ] as never[]
    expect(byShow(cards, 'archived').map((c: { id: number }) => c.id)).toEqual([2])
    expect(byShow(cards, 'worth').map((c: { id: number }) => c.id)).toEqual([1])
    expect(byShow(cards, 'current').map((c: { id: number }) => c.id)).toEqual([1])
    expect(byShow(cards, 'all')).toHaveLength(2)
  })
})
