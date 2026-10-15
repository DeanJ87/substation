// useChosen (spec 016 U6 with spec 018): a choice the shared scope has hidden drops out of what is acted on.
import { act, renderHook } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { useChosen } from './BulkBar'

describe('useChosen', () => {
  it('keeps only the chosen ids still shown', () => {
    const { result, rerender } = renderHook(({ shown }) => useChosen<number>(shown), {
      initialProps: { shown: [1, 2, 3] },
    })
    act(() => result.current.setAll([1, 2, 3], true))
    expect([...result.current.chosen]).toEqual([1, 2, 3])
    rerender({ shown: [2] })
    expect([...result.current.chosen]).toEqual([2])
  })

  it('without a shown list keeps every choice', () => {
    const { result } = renderHook(() => useChosen<number>())
    act(() => result.current.toggle(7))
    expect([...result.current.chosen]).toEqual([7])
  })
})
