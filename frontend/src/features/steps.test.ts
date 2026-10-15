import { describe, expect, it } from 'vitest'
import { stepState } from './steps'

describe('stepState', () => {
  const steps = ['Calibrate', 'Register', 'Stack']
  it('finds the running step by name and reads its progress', () => {
    expect(stepState(steps, 'Calibrate (200 of 1,000)')).toEqual({
      idx: 0,
      detail: '200 of 1,000',
      frac: 0.2,
    })
    expect(stepState(steps, 'Stack')).toEqual({ idx: 2, detail: '', frac: null })
  })
  it('is nowhere for no step or an unknown one', () => {
    expect(stepState(steps, null).idx).toBe(-1)
    expect(stepState(steps, 'Registering').idx).toBe(-1)
  })
})
