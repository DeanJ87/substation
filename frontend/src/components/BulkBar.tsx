// The bar shown while several things are chosen (spec 016): how many, the actions as buttons with text, and
// Clear. A toolbar, so a keyboard reaches every action in turn; Escape clears the choice.
import { useCallback, useMemo, useState, type ReactNode } from 'react'
import { Button } from './ui'
import s from './BulkBar.module.css'
import { countText } from '../features/format'

export function BulkBar({
  count,
  noun,
  label,
  onClear,
  className,
  inset = false,
  children,
}: {
  count: number
  noun: [string, string] // one, many: ['set', 'sets']
  label: string // names the toolbar for a screen reader: "Selected calibration sets"
  onClear: () => void
  className?: string
  inset?: boolean // inside a card whose rows run edge to edge: keep off the edges
  children: ReactNode
}) {
  if (count === 0) return null
  return (
    // Escape anywhere in the toolbar clears; the bar itself takes focus only from script
    <div
      className={[s.bar, inset && s.inset, className].filter(Boolean).join(' ')}
      role="toolbar"
      aria-label={label}
      tabIndex={-1}
      onKeyDown={(e) => {
        if (e.key === 'Escape') onClear()
      }}
    >
      <strong aria-live="polite">
        {countText(count)} {count === 1 ? noun[0] : noun[1]} selected
      </strong>
      <div className={s.actions}>
        {children}
        <Button onClick={onClear}>Clear</Button>
      </div>
    </div>
  )
}

/** A set of chosen ids, with toggle, choose-these and clear. Given the ids `shown`, a choice no longer shown (the
 *  shared scope narrowed the list, spec 018) drops out, so an action never reaches what the page doesn't show. */
export function useChosen<T>(shown?: readonly T[]) {
  const [all, setChosen] = useState<Set<T>>(() => new Set())
  const chosen = useMemo(() => {
    if (!shown) return all
    const here = new Set(shown)
    return new Set([...all].filter((id) => here.has(id)))
  }, [all, shown])
  const toggle = useCallback(
    (id: T) =>
      setChosen((old) => {
        const next = new Set(old)
        if (next.has(id)) next.delete(id)
        else next.add(id)
        return next
      }),
    [],
  )
  const setAll = useCallback(
    (ids: T[], on: boolean) =>
      setChosen((old) => {
        const next = new Set(old)
        for (const id of ids) {
          if (on) next.add(id)
          else next.delete(id)
        }
        return next
      }),
    [],
  )
  const clear = useCallback(() => setChosen(new Set()), [])
  return { chosen, toggle, setAll, clear }
}

/** A checkbox that chooses a row; clicks stay in the box so a clickable row doesn't also open. */
export function ChooseBox({
  checked,
  onChange,
  label,
  mixed = false,
}: {
  checked: boolean
  onChange: (on: boolean) => void
  label: string
  mixed?: boolean
}) {
  return (
    <input
      type="checkbox"
      className={s.box}
      checked={checked}
      aria-label={label}
      aria-checked={mixed ? 'mixed' : checked}
      ref={(el) => {
        if (el) el.indeterminate = mixed
      }}
      onClick={(e) => e.stopPropagation()}
      onKeyDown={(e) => e.stopPropagation()}
      onChange={(e) => onChange(e.target.checked)}
    />
  )
}
