import { QueryClient } from '@tanstack/react-query'
import { describe, expect, it } from 'vitest'
import { optimistic, patchDeep, patchItems } from './optimistic'

type Sub = { sha: string; verdict: string }

describe('optimistic updates', () => {
  it('patch the matching items of a list, or of every page, and can drop them', () => {
    const list: Sub[] = [
      { sha: 'a', verdict: 'auto' },
      { sha: 'b', verdict: 'auto' },
    ]
    const accept = (x: Sub) => ({ ...x, verdict: 'accept' })
    expect(patchItems<Sub>(list, (x) => x.sha === 'b', accept)).toEqual([
      list[0],
      { sha: 'b', verdict: 'accept' },
    ])
    expect(
      patchItems<Sub>(
        { pages: [list] },
        (x) => x.sha === 'a',
        () => null,
      ),
    ).toEqual({ pages: [[list[1]]] })
    expect(patchItems<Sub>(undefined, () => true, accept)).toBeUndefined()
  })
  it('patch nested items and keep unchanged branches the same object', () => {
    const old = { sessions: [{ subs: [{ sha: 'a', verdict: 'auto' }] }, { subs: [] }], total: 1 }
    const out = patchDeep(
      old,
      (x) => x.sha === 'a',
      (x) => ({ ...x, verdict: 'reject' }),
    ) as typeof old
    expect(out.sessions[0].subs[0].verdict).toBe('reject')
    expect(out.sessions[1]).toBe(old.sessions[1])
    expect(
      patchDeep(
        old,
        () => false,
        (x) => x,
      ),
    ).toBe(old)
  })
  it('change the cache at once and put it back when the server says no', async () => {
    const qc = new QueryClient()
    qc.setQueryData(['subs', 1], [{ sha: 'a', verdict: 'auto' }])
    const hooks = optimistic<string>(qc, (sha) => [
      [
        ['subs'],
        (old) =>
          patchItems<Sub>(
            old,
            (x) => x.sha === sha,
            (x) => ({ ...x, verdict: 'accept' }),
          ),
      ],
    ])
    const ctx = await hooks.onMutate('a')
    expect(qc.getQueryData(['subs', 1])).toEqual([{ sha: 'a', verdict: 'accept' }])
    hooks.onError(new Error('no'), 'a', ctx)
    expect(qc.getQueryData(['subs', 1])).toEqual([{ sha: 'a', verdict: 'auto' }])
    hooks.onSettled(undefined, null, 'a')
    expect(qc.getQueryState(['subs', 1])?.isInvalidated).toBe(true)
  })
})
