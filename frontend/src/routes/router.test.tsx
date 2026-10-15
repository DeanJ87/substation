import { cleanup } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'
import { SHA } from '../test/fakeApi'
import { renderRoute } from '../test/renderRoute'

afterEach(cleanup)

describe('links carry only search values the page understands', () => {
  it('dataset: known tab, a real sub hash, the flagged filter', async () => {
    const { router } = await renderRoute(`/datasets/1?tab=quality&sub=${SHA}&show=flagged&night=2026-10-01`)
    expect(router.state.location.search).toEqual({
      tab: 'quality',
      sub: SHA,
      show: 'flagged',
      night: '2026-10-01',
    })
  })
  it('dataset: drops an unknown tab and a malformed hash', async () => {
    const { router } = await renderRoute('/datasets/1?tab=bogus&sub=xyz&show=all')
    expect(router.state.location.search).toEqual({})
  })
  it('collection: nights and a place from the map', async () => {
    const { router } = await renderRoute(
      '/collections/1?tab=sessions&nights=2026-10-01,2026-10-02&at=51.5,-0.1',
    )
    expect(router.state.location.search).toEqual({
      tab: 'sessions',
      nights: '2026-10-01,2026-10-02',
      at: '51.5,-0.1',
    })
    const bad = await renderRoute('/collections/1?nights=<script>&at=here')
    expect(bad.router.state.location.search).toEqual({})
  })
  it('night and review', async () => {
    const night = await renderRoute(`/nights/2026-10-01?site=home&sub=${SHA}`)
    expect(night.router.state.location.search).toEqual({ site: 'home', sub: SHA })
    const review = await renderRoute('/review?dataset=7')
    expect(review.router.state.location.search).toEqual({ dataset: 7 })
  })
  it('the old queue page goes to Activity', async () => {
    const { router } = await renderRoute('/queue')
    expect(router.state.location.pathname).toBe('/activity')
  })
})
