import { cleanup, fireEvent, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'
import { fakeFor, SHA } from '../../test/fakeApi'
import { forgetLevels } from './levels'
import { renderRoute } from '../../test/renderRoute'

afterEach(() => {
  cleanup()
  forgetLevels()
  window.localStorage.clear()
})

const FIRST = SHA // the fake dataset lists two subs: this one, then the second
const SECOND = 'cd'.repeat(32)

// both subs have a preview, so the levels sliders show
const withPreview = Object.fromEntries(
  [FIRST, SECOND].map((sha) => {
    const p = fakeFor('GET', `/frames/${sha}/processing`)
    return [
      `GET /frames/${sha}/processing`,
      { ...p, sub: { ...(p.sub as object), sha256: sha, has_preview: true } },
    ]
  }),
)

async function viewer(at: string) {
  const r = await renderRoute(`/datasets/1?sub=${at}`, withPreview)
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
  it('binning the last sub steps back to the one before, not to the binned one', async () => {
    const { router } = await viewer(SECOND)
    fireEvent.click(screen.getByRole('button', { name: 'Bin' }))
    fireEvent.click(await screen.findByRole('button', { name: 'Bin', hidden: false }))
    await waitFor(() => expect(router.state.location.search).toMatchObject({ sub: FIRST }))
  })
})

describe('sub viewer display levels (012-DR-08)', () => {
  const black = () => screen.getByRole('slider', { name: 'Black point' })
  it('the black point slider is labelled and says its value', async () => {
    await viewer(FIRST)
    fireEvent.change(black(), { target: { value: '12' } })
    expect(black()).toHaveAttribute('aria-valuetext', 'Black point +12')
    expect(screen.getByRole('slider', { name: 'Brightness' })).toHaveAttribute(
      'aria-valuetext',
      'Brightness 0',
    )
    // the preview is drawn through the levels filter
    expect(screen.getByAltText(/^Preview of/).style.filter).toMatch(/^url\("?#sub-levels-/)
  })
  it('holds while stepping with K, and Reset puts it back', async () => {
    const { router } = await viewer(FIRST)
    fireEvent.change(black(), { target: { value: '20' } })
    fireEvent.keyDown(document.body, { key: 'k' })
    await waitFor(() => expect(router.state.location.search).toMatchObject({ sub: SECOND }))
    await waitFor(() => expect(black()).toHaveValue('20'))
    fireEvent.click(screen.getByRole('button', { name: 'Reset' }))
    expect(black()).toHaveValue('0')
    expect(screen.getByAltText(/^Preview of/).style.filter).toBe('')
  })
  it('[ and ] nudge the black point and \\ resets it', async () => {
    await viewer(FIRST)
    fireEvent.keyDown(document.body, { key: ']' })
    fireEvent.keyDown(document.body, { key: ']' })
    expect(black()).toHaveValue('4')
    fireEvent.keyDown(document.body, { key: '[' })
    expect(black()).toHaveValue('2')
    // on the slider itself too
    fireEvent.keyDown(black(), { key: ']' })
    expect(black()).toHaveValue('4')
    fireEvent.keyDown(document.body, { key: '\\' })
    expect(black()).toHaveValue('0')
  })
  it('is remembered per dataset and filter in this browser', async () => {
    await viewer(FIRST)
    fireEvent.change(black(), { target: { value: '30' } })
    const stored = Object.keys(window.localStorage).filter((k) => k.startsWith('substation.sub-levels.'))
    expect(stored).toHaveLength(1)
    expect(JSON.parse(window.localStorage.getItem(stored[0])!)).toEqual({ black: 30, bright: 0 })
    cleanup()
    forgetLevels()
    await viewer(SECOND)
    expect(black()).toHaveValue('30')
  })
})
