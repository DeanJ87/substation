import { cleanup, fireEvent, screen, waitFor, within } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'
import { fakeFor } from '../../test/fakeApi'
import { renderRoute } from '../../test/renderRoute'

afterEach(cleanup)

const LIST = {
  folder: '/data/substation/backups',
  writable: true,
  running: false,
  backups: [
    {
      name: 'substation-backup-2026-10-15_033000.tar.gz',
      size_bytes: 48_211_234,
      made_at: '2026-10-15T03:30:41Z',
    },
  ],
}

async function open(list = LIST) {
  const r = await renderRoute('/settings?tab=backups#backups', {
    'GET /settings': { ...fakeFor('GET', '/settings'), can_edit: true },
    'GET /backups': list,
    'POST /backups': { queued: true, note: 'Backing up.' },
    'POST /backups/substation-backup-2026-10-15_033000.tar.gz/restore': { queued: true, note: 'Restoring' },
  })
  await screen.findByText(/substation-backup-2026-10-15_033000\.tar\.gz/)
  return r
}

describe('Settings → Backups', () => {
  it('lists backups with their size and a download link', async () => {
    await open()
    expect(screen.getByText(/48\.2 MB/)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Download' })).toHaveAttribute(
      'href',
      '/api/v1/backups/substation-backup-2026-10-15_033000.tar.gz/download',
    )
  })
  it('restores only once "restore" is typed', async () => {
    const { api } = await open()
    fireEvent.click(screen.getByRole('button', { name: 'Restore…' }))
    const go = screen.getByRole('button', { name: 'Restore this backup' })
    const box = screen.getByRole('textbox', { name: 'Type restore to confirm' })
    expect(go).toBeDisabled()
    fireEvent.change(box, { target: { value: 'restor' } })
    expect(go).toBeDisabled()
    fireEvent.change(box, { target: { value: 'Restore ' } })
    expect(go).toBeEnabled()
    fireEvent.click(go)
    await waitFor(() =>
      expect(api.calls).toContainEqual({
        method: 'POST',
        path: '/backups/substation-backup-2026-10-15_033000.tar.gz/restore',
        body: { confirm: 'Restore ' },
      }),
    )
  })
  it('backs up now, and says when the folder can’t be written', async () => {
    const { api } = await open({ ...LIST, writable: false })
    expect(screen.getByRole('alert')).toHaveTextContent("can't write to /data/substation/backups")
    fireEvent.click(screen.getByRole('button', { name: 'Back up now' }))
    await waitFor(() =>
      expect(api.calls.some((c) => c.method === 'POST' && c.path === '/backups')).toBe(true),
    )
  })
  it('shows when there are none yet', async () => {
    await renderRoute('/settings?tab=backups#backups', { 'GET /backups': { ...LIST, backups: [] } })
    const section = await screen.findByText('No backups yet.')
    expect(within(section.parentElement!).queryByRole('link')).not.toBeInTheDocument()
  })
})
