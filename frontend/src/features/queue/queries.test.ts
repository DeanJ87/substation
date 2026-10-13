import { describe, expect, it } from 'vitest'
import { etaText } from './queries'

describe('etaText', () => {
  it('reads naturally', () => {
    expect(etaText(null)).toBeNull()
    expect(etaText(30)).toBe('under a minute')
    expect(etaText(6 * 60)).toBe('about 6 min')
    expect(etaText(2 * 3600 + 5 * 60)).toBe('about 2 h 05 min')
  })
})
