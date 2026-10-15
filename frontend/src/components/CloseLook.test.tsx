import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { installFakeApi, SHA } from '../test/fakeApi'
import { CloseLook } from './CloseLook'

afterEach(cleanup)

function look(mode: 'full' | 'inspector' = 'full') {
  installFakeApi({
    [`GET /frames/${SHA}/view`]: { ready: true, full: '/media/full.jpg', inspector: '/media/insp.jpg' },
  })
  const onClose = vi.fn()
  const onMode = vi.fn()
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={qc}>
      <CloseLook
        target={{ kind: 'sub', sha: SHA }}
        name="sub_0001"
        mode={mode}
        onMode={onMode}
        onClose={onClose}
      />
    </QueryClientProvider>,
  )
  return { onClose, onMode }
}

const shown = () => screen.getByRole('group', { name: 'Zoom' }).querySelector('[aria-live]')?.textContent

describe('CloseLook', () => {
  it('opens at 100% and zooms with the buttons, never below fit', () => {
    look()
    expect(shown()).toBe('100%')
    fireEvent.click(screen.getByRole('button', { name: 'Zoom in' }))
    expect(shown()).toBe('125%')
    fireEvent.click(screen.getByRole('button', { name: 'Zoom out' }))
    fireEvent.click(screen.getByRole('button', { name: 'Zoom out' }))
    expect(shown()).toBe('100%') // nothing to fit yet, so 100% is as far out as it goes
    fireEvent.click(screen.getByRole('button', { name: 'Fit' }))
    expect(screen.getByRole('button', { name: 'Fit' })).toHaveAttribute('aria-pressed', 'true')
  })
  it('answers the keys: + − 0 1, X for the inspector, Esc to close', () => {
    const { onClose, onMode } = look()
    fireEvent.keyDown(window, { key: '+' })
    fireEvent.keyDown(window, { key: '=' })
    expect(shown()).toBe('156%')
    fireEvent.keyDown(window, { key: '-' })
    expect(shown()).toBe('125%')
    fireEvent.keyDown(window, { key: '1' })
    expect(screen.getByRole('button', { name: '100%' })).toHaveAttribute('aria-pressed', 'true')
    fireEvent.keyDown(window, { key: '0' })
    expect(screen.getByRole('button', { name: 'Fit' })).toHaveAttribute('aria-pressed', 'true')
    fireEvent.keyDown(window, { key: 'x' })
    expect(onMode).toHaveBeenCalledWith('inspector')
    fireEvent.keyDown(window, { key: 'Escape' })
    expect(onClose).toHaveBeenCalled()
  })
  it('has no zoom controls in the inspector', () => {
    look('inspector')
    expect(screen.queryByRole('group', { name: 'Zoom' })).not.toBeInTheDocument()
  })
})
