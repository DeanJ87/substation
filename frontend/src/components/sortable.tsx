// Sortable tables (006-DR-23): click a heading to sort by it, again to reverse; the sorted heading shows ▲ or ▼
// and reads its order to screen readers (aria-sort). Values sort as numbers when they are numbers, else as text
// in natural order ("Panel 2" before "Panel 10"); missing values go last either way.
import { useMemo, useState, type ReactNode } from 'react'
import s from './sortable.module.css'

export type SortKey<T> = (row: T) => string | number | null | undefined

export function useSort<T>(
  rows: T[],
  keys: Record<string, SortKey<T>>,
  initial?: { key: string; desc?: boolean },
) {
  const [sort, setSort] = useState<{ key: string; desc: boolean } | null>(
    initial ? { key: initial.key, desc: !!initial.desc } : null,
  )
  const sorted = useMemo(() => {
    if (!sort || !keys[sort.key]) return rows
    const get = keys[sort.key]
    const collator = new Intl.Collator('en-GB', { numeric: true, sensitivity: 'base' })
    return [...rows].sort((a, b) => {
      const x = get(a)
      const y = get(b)
      if (x == null || x === '') return y == null || y === '' ? 0 : 1
      if (y == null || y === '') return -1
      const c =
        typeof x === 'number' && typeof y === 'number' ? x - y : collator.compare(String(x), String(y))
      return sort.desc ? -c : c
    })
    // keys are recreated each render; the sort only depends on their behaviour, which is stable per table
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [rows, sort])
  /** A sortable heading cell: `th('name', 'Dataset')`. A render function, not a component, so the button keeps
   * keyboard focus when the table re-sorts. */
  const th = (k: string, children: ReactNode, className?: string) => {
    const on = sort?.key === k
    return (
      <th key={k} aria-sort={on ? (sort.desc ? 'descending' : 'ascending') : 'none'} className={className}>
        <button
          type="button"
          className={s.sortButton}
          onClick={() => setSort(on ? { key: k, desc: !sort.desc } : { key: k, desc: false })}
        >
          {children}
          <span className={on ? s.arrowOn : s.arrow} aria-hidden="true">
            {on && sort.desc ? '▼' : '▲'}
          </span>
        </button>
      </th>
    )
  }
  return { sorted, th, sort }
}
