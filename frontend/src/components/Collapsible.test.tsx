import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { SettingsSection } from '../features/settings/SettingsSection'
import { Collapsible } from './Collapsible'

beforeEach(() => localStorage.clear())
afterEach(() => {
  cleanup()
  window.location.hash = ''
})

describe('Collapsible', () => {
  it('folds away and remembers it', () => {
    render(
      <Collapsible id="t" title="Workers" meta="3">
        <p>inside</p>
      </Collapsible>,
    )
    const head = screen.getByRole('button', { name: 'Workers' })
    expect(head).toHaveAttribute('aria-expanded', 'true')
    fireEvent.click(head)
    expect(screen.queryByText('inside')).not.toBeInTheDocument()
    expect(localStorage.getItem('sst.open.t')).toBe('0')
    cleanup()
    render(
      <Collapsible id="t" title="Workers">
        <p>inside</p>
      </Collapsible>,
    )
    expect(screen.getByRole('button', { name: 'Workers' })).toHaveAttribute('aria-expanded', 'false')
  })
  it('can start closed', () => {
    render(
      <Collapsible id="u" title="More" defaultOpen={false}>
        <p>inside</p>
      </Collapsible>,
    )
    expect(screen.queryByText('inside')).not.toBeInTheDocument()
  })
  it('a settings section linked to directly opens even if it was closed', () => {
    localStorage.setItem('sst.open.settings-backups', '0')
    window.location.hash = '#backups'
    render(
      <SettingsSection id="backups" title="Backups">
        <p>inside</p>
      </SettingsSection>,
    )
    expect(screen.getByText('inside')).toBeInTheDocument()
    expect(document.getElementById('backups')).not.toBeNull()
  })
})
