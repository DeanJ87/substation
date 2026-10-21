import { cleanup, fireEvent, screen, waitFor, within } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'
import { fakeFor } from '../../test/fakeApi'
import { renderRoute } from '../../test/renderRoute'

afterEach(cleanup)

const TOKEN = {
  id: 1,
  name: 'dean0 render',
  scope: 'render',
  hint: 'abcd',
  created_at: '2026-10-20T21:30:00Z',
  expires_at: null,
  last_used_at: null,
  revoked_at: null,
  active: true,
}
const SECRET = 'sst_not-a-real-token'
const ADMIN = { ...fakeFor('GET', '/settings'), can_edit: true }

async function open(settings: object = ADMIN) {
  const r = await renderRoute('/settings#tokens', {
    'GET /settings': settings,
    'GET /tokens': [TOKEN],
    'POST /tokens': (b: unknown) => ({
      token: { ...TOKEN, id: 2, name: (b as { name: string }).name, hint: 'wxyz' },
      secret: SECRET,
    }),
    'POST /tokens/1/revoke': { ...TOKEN, active: false, revoked_at: '2026-10-21T08:00:00Z' },
  })
  return r
}

describe('Settings → API tokens (spec 020)', () => {
  it('lists tokens by name and hint, never the secret', async () => {
    await open()
    const row = (await screen.findByText('dean0 render')).closest('tr')!
    expect(row).toHaveTextContent('…abcd')
    expect(row).toHaveTextContent('never') // last used
    expect(row).toHaveTextContent('no expiry')
    expect(row).toHaveTextContent('Active')
  })

  it('shows a new token once, with how to use it, until it is put away', async () => {
    const { api } = await open()
    await screen.findByText('dean0 render')
    fireEvent.change(screen.getByRole('textbox', { name: 'Name' }), { target: { value: 'renderer' } })
    fireEvent.click(screen.getByRole('button', { name: 'Create token' }))
    const box = await screen.findByRole('region', { name: 'New token' })
    expect(api.calls).toContainEqual({
      method: 'POST',
      path: '/tokens',
      body: { name: 'renderer', expires_at: null },
    })
    expect(box).toHaveTextContent("Copy this token now. You won't see it again.")
    expect(within(box).getByRole('textbox', { name: 'Token for renderer' })).toHaveValue(SECRET)
    expect(box).toHaveTextContent(`Authorization: Bearer ${SECRET}`)
    expect(box).toHaveTextContent('/api/v1/render/projects')
    fireEvent.click(within(box).getByRole('button', { name: "I've copied it" }))
    expect(screen.queryByRole('region', { name: 'New token' })).not.toBeInTheDocument()
    expect(screen.queryByDisplayValue(SECRET)).not.toBeInTheDocument()
    expect(document.body).not.toHaveTextContent(SECRET)
  })

  it('sends an expiry date as the end of that day', async () => {
    const { api } = await open()
    await screen.findByText('dean0 render')
    fireEvent.change(screen.getByRole('textbox', { name: 'Name' }), { target: { value: 'renderer' } })
    fireEvent.change(screen.getByLabelText(/Expires/), { target: { value: '2027-01-31' } })
    fireEvent.click(screen.getByRole('button', { name: 'Create token' }))
    await waitFor(() =>
      expect(api.calls).toContainEqual({
        method: 'POST',
        path: '/tokens',
        body: { name: 'renderer', expires_at: new Date('2027-01-31T23:59:59').toISOString() },
      }),
    )
  })

  it('revokes only after asking in the page', async () => {
    const { api } = await open()
    const row = (await screen.findByText('dean0 render')).closest('tr')!
    fireEvent.click(within(row).getByRole('button', { name: 'Revoke' }))
    const ask = within(row).getByRole('group', { name: 'Confirm' })
    expect(ask).toHaveTextContent('Revoke dean0 render? Apps using it stop working at once.')
    expect(api.calls.some((c) => c.path === '/tokens/1/revoke')).toBe(false)
    fireEvent.click(within(ask).getByRole('button', { name: 'Revoke' }))
    await waitFor(() =>
      expect(api.calls).toContainEqual({ method: 'POST', path: '/tokens/1/revoke', body: null }),
    )
  })

  it('is for admins only: nothing is asked of the server for anyone else', async () => {
    const { api } = await open({ ...ADMIN, can_edit: false })
    await screen.findByRole('button', { name: 'API tokens' })
    expect(screen.queryByRole('button', { name: 'Create token' })).not.toBeInTheDocument()
    expect(api.calls.some((c) => c.path === '/tokens')).toBe(false)
  })
})

describe('Settings → Library: finished work and the site (spec 020)', () => {
  it('saves the installation site’s region and Bortle class', async () => {
    const { api } = await renderRoute('/settings#sources', {
      'GET /settings': { ...ADMIN, site_region: '', site_bortle: null },
    })
    const region = (await screen.findAllByRole('textbox', { name: 'Region' }))[0]
    fireEvent.change(region, { target: { value: 'Moorland' } })
    const form = region.closest('form')!
    fireEvent.change(within(form).getByRole('combobox', { name: 'Bortle class' }), { target: { value: '3' } })
    fireEvent.click(within(form).getByRole('button', { name: 'Save site' }))
    await waitFor(() =>
      expect(api.calls).toContainEqual(
        expect.objectContaining({
          method: 'PATCH',
          path: '/settings',
          body: expect.objectContaining({ site_region: 'Moorland', site_bortle: 3 }),
        }),
      ),
    )
  })

  it('edits the default processing steps', async () => {
    const { api } = await renderRoute('/settings#finished', {
      'GET /settings': { ...ADMIN, default_processing: ['GraXpert'] },
      'PUT /finished/defaults/processing': (b: unknown) => (b as { steps: string[] }).steps,
    })
    const list = await screen.findByRole('list', { name: 'Default processing steps' })
    expect(within(list).getByRole('textbox', { name: 'Step 1' })).toHaveValue('GraXpert')
    fireEvent.change(screen.getByRole('textbox', { name: 'New step' }), {
      target: { value: 'NoiseXTerminator' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Add step' }))
    fireEvent.click(screen.getByRole('button', { name: 'Save steps' }))
    await waitFor(() =>
      expect(api.calls).toContainEqual({
        method: 'PUT',
        path: '/finished/defaults/processing',
        body: { steps: ['GraXpert', 'NoiseXTerminator'] },
      }),
    )
  })
})
