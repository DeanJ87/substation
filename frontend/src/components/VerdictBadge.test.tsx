import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { VERDICTS, VerdictBadge, VerdictIcon, type VerdictState } from './VerdictBadge'

const states = Object.keys(VERDICTS) as VerdictState[]

describe('verdict system', () => {
  it('has the seven states from the design', () => {
    expect(states).toEqual(['accept', 'down', 'reject', 'await', 'integ', 'stale', 'recon'])
  })

  it('gives every state a distinct shape-and-glyph pair, so colour is never the only cue', () => {
    const silhouettes = new Set(
      states.map((s) => `${VERDICTS[s].shape}|${VERDICTS[s].glyph}|${VERDICTS[s].filled}`),
    )
    expect(silhouettes.size).toBe(states.length)
  })

  it('fills final decisions and outlines states that will change', () => {
    expect(states.filter((s) => VERDICTS[s].filled)).toEqual(['accept', 'down', 'reject'])
  })

  it.each(states)('renders %s with an accessible name', (s) => {
    render(<VerdictIcon state={s} />)
    expect(screen.getByRole('img', { name: VERDICTS[s].name })).toBeInTheDocument()
  })

  it('renders a badge with its label', () => {
    render(<VerdictBadge state="recon" />)
    expect(screen.getByText('Needs reconciliation')).toBeInTheDocument()
  })
})
