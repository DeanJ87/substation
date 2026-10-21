import { cleanup, fireEvent, screen, waitFor, within } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'
import { fakeFor } from '../../test/fakeApi'
import { renderRoute } from '../../test/renderRoute'

afterEach(cleanup)

const WHY = 'Mounted read-only. Mount it read-write (SUBSTATION_LIBRARY_2_MODE=rw) to allow this.'
const base = (fakeFor('GET', '/libraries') as unknown as object[])[0]
const LIBS = [
  {
    ...base,
    id: 1,
    name: 'active',
    mount_path: '/data/library/active',
    enabled: true,
    writable: true,
    read_only_reason: null,
    role: 'active',
    archive_to: null,
    allow_delete: false,
  },
  {
    ...base,
    id: 2,
    name: 'archive',
    mount_path: '/data/library/archive',
    enabled: true,
    writable: false,
    read_only_reason: WHY,
    role: '',
    archive_to: null,
    allow_delete: false,
  },
]

async function open() {
  const r = await renderRoute('/settings#library', {
    'GET /settings': { ...fakeFor('GET', '/settings'), can_edit: true },
    'GET /libraries': LIBS,
    'PATCH /libraries/1': (b: unknown) => ({ ...LIBS[0], ...(b as object) }),
    'PATCH /libraries/2': (b: unknown) => ({ ...LIBS[1], ...(b as object) }),
  })
  await screen.findAllByText('/data/library/archive')
  return r
}

describe('Settings → Library: writable libraries (specs 011, 013)', () => {
  it('says whether each library is mounted read-write', async () => {
    await open()
    expect(screen.getByText('Mounted read-write')).toBeInTheDocument()
    expect(screen.getByText('Mounted read-only')).toBeInTheDocument()
  })

  it('a read-only library may only be Completed: Active and Archive stay in view, disabled, with the reason', async () => {
    const { api } = await open()
    const roles = screen.getAllByRole('combobox', { name: /Role/ })
    expect(roles[0]).toBeEnabled()
    expect(roles[1]).toBeEnabled()
    expect(roles[1]).toHaveAccessibleDescription(WHY)
    const options = within(roles[1]).getAllByRole('option') as HTMLOptionElement[]
    expect(options.map((o) => [o.value, o.disabled])).toEqual([
      ['', false],
      ['active', true],
      ['archive', true],
      ['completed', false],
    ])
    fireEvent.change(roles[1], { target: { value: 'completed' } })
    await waitFor(() =>
      expect(api.calls).toContainEqual({
        method: 'PATCH',
        path: '/libraries/2',
        body: { role: 'completed' },
      }),
    )
  })

  it('a library’s site takes a region and Bortle class for the renderer (spec 020)', async () => {
    const { api } = await open()
    fireEvent.click(screen.getByRole('button', { name: 'Edit the site of active' }))
    const form = screen.getByRole('form', { name: 'Site of active' })
    fireEvent.change(within(form).getByRole('textbox', { name: 'Region' }), { target: { value: 'Moorland' } })
    fireEvent.change(within(form).getByRole('combobox', { name: 'Bortle class' }), { target: { value: '4' } })
    fireEvent.click(within(form).getByRole('button', { name: 'Save site' }))
    await waitFor(() =>
      expect(api.calls).toContainEqual({
        method: 'PATCH',
        path: '/libraries/1',
        body: { site: expect.objectContaining({ region: 'Moorland', bortle: 4 }) },
      }),
    )
  })

  it('the bin’s delete switch is disabled with the reason beside it, not unexplained', async () => {
    await open()
    const boxes = screen.getAllByRole('checkbox', { name: 'SubStation may delete files here' })
    expect(boxes[0]).toBeEnabled()
    expect(boxes[1]).toBeDisabled()
    expect(boxes[1]).toHaveAccessibleDescription(WHY)
  })

  it('an active library chooses its archive among archive libraries', async () => {
    const { api } = await open()
    const row = screen.getAllByRole('combobox', { name: /Role/ })[0].closest('li')!
    const target = within(row).getByRole('combobox', { name: /Archives to/ })
    expect(target).toBeDisabled() // no library is an archive yet
    expect(row).toHaveTextContent('Set another library as an archive first.')
    fireEvent.change(screen.getAllByRole('combobox', { name: /Role/ })[0], { target: { value: '' } })
    await waitFor(() =>
      expect(api.calls).toContainEqual({ method: 'PATCH', path: '/libraries/1', body: { role: '' } }),
    )
  })
})
