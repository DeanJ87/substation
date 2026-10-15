import { act, cleanup, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { Toasts, toast } from './Toasts'

afterEach(() => {
  cleanup()
  vi.useRealTimers()
})

describe('toasts', () => {
  it('show once however often they are raised, and go away', () => {
    vi.useFakeTimers()
    render(<Toasts />)
    act(() => {
      toast('Path copied')
      toast('Path copied')
    })
    expect(screen.getAllByText('Path copied')).toHaveLength(1)
    act(() => {
      vi.advanceTimersByTime(4000)
    })
    expect(screen.queryByText('Path copied')).not.toBeInTheDocument()
  })
  it('failures stay longer', () => {
    vi.useFakeTimers()
    render(<Toasts />)
    act(() => toast("Couldn't save that", true))
    act(() => {
      vi.advanceTimersByTime(4000)
    })
    expect(screen.getByText("Couldn't save that")).toBeInTheDocument()
    act(() => {
      vi.advanceTimersByTime(4000)
    })
    expect(screen.queryByText("Couldn't save that")).not.toBeInTheDocument()
  })
})
