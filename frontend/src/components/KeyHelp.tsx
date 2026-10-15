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
    match: /^\/datasets\//,
    title: 'Dataset and sub viewer',
    keys: [
      ['Enter or double-click', 'Open the selected sub in the viewer'],
      ['J or ←', 'Viewer: previous sub'],
      ['K or →', 'Viewer: next sub in the list'],
      ['A', 'Accept (selected subs, or the sub in the viewer)'],
      ['W', 'Down-weight'],
      ['R', 'Reject'],
      ['U', 'Revert to auto'],
      [
        'Z',
        'Viewer: full-size view (wheel or + − to zoom, drag to pan, 0 fit, 1 100%, double-click; Esc: close)',
      ],
      ['X', 'Viewer: aberration inspector'],
      ['Esc', 'Close the viewer'],
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
