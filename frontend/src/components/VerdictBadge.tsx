// The seven-state verdict system from the brand guidelines (section 07). Each state has its own shape and
// glyph, so colour is a third cue, never the only one (constitution III); filled shapes are final
// decisions, outlined shapes are states that will change. Paths are the design's 16-unit artwork. Colours are the
// status tokens (007-DR-38): low-chroma, clear of the filter palette; rejected is grey, never red.
import styles from './VerdictBadge.module.css'

export type VerdictState = 'accept' | 'down' | 'reject' | 'await' | 'integ' | 'stale' | 'recon'

interface Def {
  name: string
  token: string
  filled: boolean
  shape: string
  glyph: string
  dash?: string
}

const circle = 'M8 1.75a6.25 6.25 0 1 1 0 12.5a6.25 6.25 0 1 1 0-12.5z'
const square = 'M2.75 1.75h10.5a1 1 0 0 1 1 1v10.5a1 1 0 0 1-1 1H2.75a1 1 0 0 1-1-1V2.75a1 1 0 0 1 1-1z'

export const VERDICTS: Record<VerdictState, Def> = {
  accept: { name: 'Accepted', token: 'st-kept', filled: true, shape: circle, glyph: 'M5.1 8.3l2 2l3.9-4.3' },
  down: {
    name: 'Down-weighted',
    token: 'st-down',
    filled: true,
    shape: 'M1.5 2.25h13L8 14.5z',
    glyph: 'M5.6 5.4h4.8',
  },
  reject: {
    name: 'Rejected',
    token: 'st-rejected',
    filled: true,
    shape: square,
    glyph: 'M5.6 5.6l4.8 4.8M10.4 5.6l-4.8 4.8',
  },
  await: {
    name: 'Awaiting calibration',
    token: 'dim',
    filled: false,
    shape: circle,
    glyph: 'M8 5v3.2h2.4',
    dash: '2.2 1.6',
  },
  integ: {
    name: 'Integrating',
    token: 'st-pending',
    filled: false,
    shape: 'M8 1.5l5.6 3.25v6.5L8 14.5l-5.6-3.25v-6.5z',
    glyph: 'M5.4 6.2h5.2M5.4 8h5.2M5.4 9.8h5.2',
  },
  stale: { name: 'Stale', token: 'muted', filled: false, shape: square, glyph: 'M5.5 10.5l5-5' },
  recon: {
    name: 'Needs reconciliation',
    token: 'violet',
    filled: false,
    shape: 'M8 1.25l6.75 6.75L8 14.75L1.25 8z',
    glyph: 'M8 5v3.4M8 10.8v.1',
  },
}

export function VerdictIcon({
  state,
  size = 16,
  title,
}: {
  state: VerdictState
  size?: number
  title?: string
}) {
  const v = VERDICTS[state]
  const colour = `var(--sst-${v.token})`
  // An empty title means the icon sits beside its own text label: decorative, so hidden from screen readers
  const a11y = title === '' ? { 'aria-hidden': true } : { role: 'img', 'aria-label': title ?? v.name }
  return (
    <svg width={size} height={size} viewBox="0 0 16 16" {...a11y}>
      <path
        d={v.shape}
        fill={v.filled ? colour : 'none'}
        stroke={colour}
        strokeWidth={1.5}
        strokeDasharray={v.dash}
        strokeLinejoin="round"
      />
      <path
        d={v.glyph}
        fill="none"
        stroke={v.filled ? 'var(--sst-bg)' : colour}
        strokeWidth={1.6}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  )
}

export function VerdictBadge({ state, label }: { state: VerdictState; label?: string }) {
  const v = VERDICTS[state]
  return (
    <span className={styles.badge} style={{ ['--badge-colour' as string]: `var(--sst-${v.token})` }}>
      <VerdictIcon state={state} title="" />
      <span>{label ?? v.name}</span>
    </span>
  )
}
