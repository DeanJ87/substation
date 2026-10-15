import { cleanup, fireEvent, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'
import { SHA } from '../../test/fakeApi'
import { renderRoute } from '../../test/renderRoute'

afterEach(cleanup)

const FIRST = SHA // the fake dataset lists two subs: this one, then the second
const SECOND = 'cd'.repeat(32)

async function viewer(at: string) {
  const r = await renderRoute(`/datasets/1?sub=${at}`)
  await screen.findByRole('dialog')
  await waitFor(() => expect(r.api.calls.some((c) => c.path === `/frames/${at}/processing`)).toBe(true))
  await new Promise((done) => setTimeout(done, 50))
  return r
}

describe('sub viewer keys (2026-10-15: J back, K on)', () => {
  it('K and → go to the next sub in the list', async () => {
    const { router } = await viewer(FIRST)
    fireEvent.keyDown(document.body, { key: 'k' })
    await waitFor(() => expect(router.state.location.search).toMatchObject({ sub: SECOND }))
  })
  it('J and ← go back', async () => {
    const { router } = await viewer(SECOND)
    fireEvent.keyDown(document.body, { key: 'ArrowLeft' })
    await waitFor(() => expect(router.state.location.search).toMatchObject({ sub: FIRST }))
  })
  it('A accepts the sub', async () => {
    const { api } = await viewer(FIRST)
    fireEvent.keyDown(document.body, { key: 'a' })
    await waitFor(() =>
      expect(api.calls.find((c) => c.method !== 'GET')?.body).toMatchObject({
        sha256s: [FIRST],
        verdict: 'accept',
      }),
    )
  })
})
