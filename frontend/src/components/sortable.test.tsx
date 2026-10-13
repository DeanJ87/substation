import { act, renderHook } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { useSort } from './sortable'

const rows = [
  { name: 'Panel 10', h: 2 },
  { name: 'Panel 2', h: null },
  { name: 'panel 1', h: 5 },
]

describe('useSort (006-DR-23)', () => {
  it('sorts text naturally, numbers as numbers, missing values last, and reverses', () => {
    const { result } = renderHook(() => useSort(rows, { name: (r) => r.name, h: (r) => r.h }))
    expect(result.current.sorted.map((r) => r.name)).toEqual(['Panel 10', 'Panel 2', 'panel 1'])
    const click = (k: string) => {
      const th = result.current.th(k, k) as { props: { children: { props: { onClick: () => void } } } }
      act(() => th.props.children.props.onClick())
    }
    click('name')
    expect(result.current.sorted.map((r) => r.name)).toEqual(['panel 1', 'Panel 2', 'Panel 10'])
    click('h')
    expect(result.current.sorted.map((r) => r.h)).toEqual([2, 5, null])
    click('h')
    expect(result.current.sorted.map((r) => r.h)).toEqual([5, 2, null])
  })
})
