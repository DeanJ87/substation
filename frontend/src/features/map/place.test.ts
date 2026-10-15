import { describe, expect, it } from 'vitest'
import { coords } from './place'

describe('coords', () => {
  it('writes hemispheres instead of signs', () => {
    expect(coords(51.4779, -0.0015)).toBe('51.478° N, 0.002° W')
    expect(coords(-33.8568, 151.2153)).toBe('33.857° S, 151.215° E')
  })
})
