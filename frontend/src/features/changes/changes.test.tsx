import { cleanup, fireEvent, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'
import { renderRoute } from '../../test/renderRoute'

afterEach(cleanup)

const CHANGE = {
  id: 7,
  kind: 'agree',
  summary: 'Agreed with 3 grades · NGC 7000 · 11 Oct 2026',
  count: 3,
  created_at: '2026-10-15T15:00:00Z',
  undone_at: null,
  by: 'admin',
  can_undo: true,
}
const UNDONE = {
  note: 'Undone: agreed with 3 grades · NGC 7000 · 11 Oct 2026.',
  change: { ...CHANGE, undone_at: '2026-10-15T15:01:00Z', can_undo: false },
}

describe('undo (spec 016)', () => {
  it('Activity lists your changes and undoes one', async () => {
    const { api } = await renderRoute('/activity', {
      'GET /changes': [CHANGE],
      'POST /changes/7/undo': UNDONE,
    })
    await screen.findByText(CHANGE.summary)
    fireEvent.click(screen.getByRole('button', { name: 'Undo' }))
    await waitFor(() =>
      expect(api.calls.some((c) => c.method === 'POST' && c.path === '/changes/7/undo')).toBe(true),
    )
    expect(await screen.findByText(UNDONE.note)).toBeInTheDocument()
  })

  it('Ctrl+Z undoes your latest change', async () => {
    const { api } = await renderRoute('/activity', {
      'GET /changes': [CHANGE],
      'POST /changes/7/undo': UNDONE,
    })
    await screen.findByText(CHANGE.summary)
    fireEvent.keyDown(document.body, { key: 'z', ctrlKey: true })
    await waitFor(() => expect(api.calls.some((c) => c.path === '/changes/7/undo')).toBe(true))
  })

  it('Ctrl+Z in a text field is left to the field', async () => {
    const { api } = await renderRoute('/activity', { 'GET /changes': [CHANGE] })
    await screen.findByText(CHANGE.summary)
    const input = document.createElement('input')
    document.body.append(input)
    fireEvent.keyDown(input, { key: 'z', ctrlKey: true })
    await new Promise((r) => setTimeout(r, 50))
    expect(api.calls.some((c) => c.path === '/changes/7/undo')).toBe(false)
    input.remove()
  })
})
