import { afterEach, describe, expect, it, vi } from 'vitest'
import { applyTheme, readTheme, toggleNight } from './theme'

afterEach(() => {
  localStorage.clear()
  document.documentElement.removeAttribute('data-theme')
  vi.restoreAllMocks()
})

describe('theme', () => {
  it('defaults to dark', () => {
    expect(readTheme()).toBe('dark')
  })

  it('applies light and night through data-theme and remembers the choice', () => {
    applyTheme('night')
    expect(document.documentElement.dataset.theme).toBe('night')
    expect(readTheme()).toBe('night')
    applyTheme('dark')
    expect(document.documentElement.hasAttribute('data-theme')).toBe(false)
  })

  it('N toggles night vision and back to the previous theme', () => {
    expect(toggleNight('light', 'light')).toBe('night')
    expect(toggleNight('night', 'light')).toBe('light')
    expect(toggleNight('night', 'night')).toBe('dark')
  })

  it('still works when storage is blocked', () => {
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new Error('blocked')
    })
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('blocked')
    })
    expect(readTheme()).toBe('dark')
    expect(() => applyTheme('light')).not.toThrow()
    expect(document.documentElement.dataset.theme).toBe('light')
  })
})
