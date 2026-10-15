import { cleanup, fireEvent, screen } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'
import { renderRoute } from '../test/renderRoute'

afterEach(cleanup)

describe('KeyHelp', () => {
  it('? lists the keys for this screen and everywhere; Escape closes it', async () => {
    await renderRoute('/datasets/1')
    fireEvent.keyDown(document.body, { key: '?' })
    const dialog = await screen.findByRole('dialog', { name: 'Keyboard' })
    expect(dialog).toHaveTextContent('Dataset and sub viewer')
    expect(dialog).toHaveTextContent('Viewer: previous sub')
    expect(dialog).toHaveTextContent('Everywhere')
    fireEvent.keyDown(document.body, { key: 'Escape' })
    expect(screen.queryByRole('dialog', { name: 'Keyboard' })).not.toBeInTheDocument()
  })
  it('shows only the everywhere keys elsewhere', async () => {
    await renderRoute('/activity')
    fireEvent.keyDown(document.body, { key: '?' })
    const dialog = await screen.findByRole('dialog', { name: 'Keyboard' })
    expect(dialog).not.toHaveTextContent('Dataset and sub viewer')
    fireEvent.click(screen.getByRole('button', { name: 'Close' }))
    expect(screen.queryByRole('dialog', { name: 'Keyboard' })).not.toBeInTheDocument()
  })
})
