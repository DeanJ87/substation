// "?" lists the keys for the screen you're on (007-DR-12). Escape or ? again closes it.
import { useRouterState } from '@tanstack/react-router'
import { useEffect, useState } from 'react'
import s from './KeyHelp.module.css'

const EVERYWHERE: [string, string][] = [
  ['/', 'Search'],
  ['N', 'Night vision'],
  ['?', 'This list'],
]
const SCREENS: { match: RegExp; title: string; keys: [string, string][] }[] = [
  {
    match: /^\/review/,
    title: 'Review',
    keys: [
      ['J or →', 'Next flagged sub'],
      ['K or ←', 'Previous flagged sub'],
      ['Space', 'Blink with best sub'],
      ['A', 'Accept'],
      ['W', 'Down-weight'],
      ['R', 'Reject'],
      ['Shift + A, W or R', 'Apply to adjacent flagged subs'],
      ['U', 'Revert to auto'],
      ['Z', '100% view (1, 2, 0: zoom; Esc: close)'],
      ['X', 'Aberration inspector'],
      ['I', 'Open sub'],
    ],
  },
  {
    match: /^\/datasets\//,
    title: 'Dataset',
    keys: [
      ['A', 'Accept'],
      ['W', 'Down-weight'],
      ['R', 'Reject'],
      ['U', 'Revert to auto'],
    ],
  },
]

export function KeyHelp() {
  const [open, setOpen] = useState(false)
  const path = useRouterState({ select: (r) => r.location.pathname })
  useEffect(() => {
    function key(e: KeyboardEvent) {
      if ((e.target as HTMLElement).closest('input, select, textarea')) return
      if (e.key === '?') {
        e.preventDefault()
        setOpen((o) => !o)
      } else if (e.key === 'Escape') setOpen(false)
    }
    window.addEventListener('keydown', key)
    return () => window.removeEventListener('keydown', key)
  }, [])
  if (!open) return null
  const screen = SCREENS.find((x) => x.match.test(path))
  return (
    <div
      className={s.backdrop}
      onClick={(e) => e.target === e.currentTarget && setOpen(false)}
      role="presentation"
    >
      <div className={s.dialog} role="dialog" aria-modal="true" aria-labelledby="keys-h">
        <h2 id="keys-h">Keyboard</h2>
        {screen && <Group title={screen.title} keys={screen.keys} />}
        <Group title="Everywhere" keys={EVERYWHERE} />
        <button type="button" className={s.close} onClick={() => setOpen(false)}>
          Close
        </button>
      </div>
    </div>
  )
}

function Group({ title, keys }: { title: string; keys: [string, string][] }) {
  return (
    <section>
      <div className={s.label}>{title}</div>
      <dl className={s.list}>
        {keys.map(([k, what]) => (
          <div key={k}>
            <dt>
              <kbd>{k}</kbd>
            </dt>
            <dd>{what}</dd>
          </div>
        ))}
      </dl>
    </section>
  )
}
