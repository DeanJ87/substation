// The shared filter bar (spec 018): free text, rig, filter and nights, written to the address so the page, its
// requests and its links all carry the same scope.
import { useQuery } from '@tanstack/react-query'
import { useEffect, useRef, useState } from 'react'
import { api, unwrap } from '../../api/client'
import { Button, Chip, DateInput, Select } from '../../components/ui'
import { isEmpty, type Scope } from './scope'
import s from './scope.module.css'
import { dateText } from '../format'
import { filterName, sortFilters } from '../../components/filters'
import { setRangeEnd } from '../cascade'

const CHIPS: [keyof Scope, string][] = [
  ['date', 'Night'],
  ['site', 'Place'],
  ['target', 'Target'],
  ['camera', 'Camera'],
  ['telescope', 'Telescope'],
  ['collection', 'Collection'],
  ['project', 'Project'],
  ['dataset', 'Dataset'],
]

const nightLabel = (d: string) => dateText(`${d}T12:00:00`)

/** The filters to offer: the page's, narrowed to the rig's when a rig is chosen (all of the rig's when the page
 * names none), plus the current choice so it stays visible. */
export function filterChoices(
  page: string[],
  rig: string[] | undefined,
  current: string | undefined,
): string[] {
  const base = rig ? (page.length ? page.filter((f) => rig.includes(f)) : rig) : page
  // the canonical filter order everywhere (C09): L R G B, Hα OIII SII, OSC, then the rest
  return sortFilters([...new Set([...base, ...(current ? [current] : [])])])
}

/** The filter select's options: a current choice the rig never shot through stays visible (a link brought it)
 * but says so and can't be chosen again, so no choice leads to an empty page. */
export function filterOptions(
  page: string[],
  rig: string[] | undefined,
  current: string | undefined,
): { value: string; label: string; disabled?: boolean }[] {
  return filterChoices(page, rig, current).map((f) =>
    rig && f === current && !rig.includes(f)
      ? { value: f, label: `${filterName(f)} (none on this rig)`, disabled: true }
      : { value: f, label: filterName(f) },
  )
}

export function ScopeBar({
  scope,
  onChange,
  filters = [],
  search,
}: {
  scope: Scope
  onChange: (next: Scope) => void
  filters?: string[]
  /** a free-text box (the scope's `q`) with this placeholder; typing asks the server once it settles */
  search?: string
}) {
  const rigs = useQuery({ queryKey: ['rigs'], queryFn: async () => unwrap(await api.GET('/rigs')) })
  const set = (patch: Partial<Scope>) => onChange({ ...scope, ...patch })
  const rig = (rigs.data ?? []).find((r) => r.id === scope.rig)
  // filters follow the rig: only what it shot through (and the page has), so no choice leads nowhere
  const offered = filterOptions(filters, rig?.filters, scope.filter)
  const pickRig = (id: number | undefined) => {
    const next = (rigs.data ?? []).find((r) => r.id === id)
    const keep = !scope.filter || !next || next.filters.includes(scope.filter)
    set({ rig: id, filter: keep ? scope.filter : undefined })
  }
  const q = scope.q ?? ''
  const [text, setText] = useState(q)
  const [seen, setSeen] = useState(q)
  // the address changed under the box (Clear, a link, back): show what it says
  if (q !== seen) {
    setSeen(q)
    if (text.trim() !== q) setText(q)
  }
  // on a phone the bar folds behind one Filters button (D18), open when something is filtered
  const [open, setOpen] = useState(false)
  const active = Object.keys(scope).filter((k) => scope[k as keyof Scope] !== undefined).length
  const timer = useRef<number | undefined>(undefined)
  useEffect(() => () => window.clearTimeout(timer.current), [])
  const type = (value: string) => {
    setText(value)
    window.clearTimeout(timer.current)
    // asks once the typing settles, not on every key
    timer.current = window.setTimeout(() => onChange({ ...scope, q: value.trim() || undefined }), 300)
  }
  return (
    <div className={s.bar} role="group" aria-label="Filters">
      <Button
        size="sm"
        className={s.toggle}
        aria-expanded={open}
        aria-controls="scope-controls"
        onClick={() => setOpen(!open)}
      >
        Filters{active ? ` · ${active}` : ''}
      </Button>
      <div id="scope-controls" className={`${s.controls} ${open ? s.open : ''}`}>
        {search !== undefined && (
          <input
            type="search"
            className={s.search}
            placeholder={search}
            value={text}
            onChange={(e) => type(e.target.value)}
            aria-label="Search"
          />
        )}
        <Select
          aria-label="Rig"
          value={scope.rig ?? ''}
          onChange={(e) => pickRig(e.target.value ? Number(e.target.value) : undefined)}
          options={[
            { value: '', label: 'Rig: All' },
            ...(rigs.data ?? []).map((r) => ({ value: r.id, label: r.name })),
          ]}
        />
        <Select
          aria-label="Filter"
          value={scope.filter ?? ''}
          onChange={(e) => set({ filter: e.target.value || undefined })}
          options={[{ value: '', label: 'Filter: All' }, ...offered]}
        />
        <span className={s.dates}>
          <DateInput
            label="From"
            value={scope.date_from}
            max={scope.date_to}
            onChange={(v) => {
              const r = setRangeEnd({ from: scope.date_from, to: scope.date_to }, 'from', v)
              set({ date_from: r.from, date_to: r.to })
            }}
          />
          <DateInput
            label="To"
            value={scope.date_to}
            min={scope.date_from}
            onChange={(v) => {
              const r = setRangeEnd({ from: scope.date_from, to: scope.date_to }, 'to', v)
              set({ date_from: r.from, date_to: r.to })
            }}
          />
        </span>
        {/* what a link brought along that the bar has no control for: shown, and removable one by one */}
        {CHIPS.filter(([k]) => scope[k] !== undefined).map(([k, label]) => (
          <Chip
            key={k}
            onRemove={() => set({ [k]: undefined })}
            removeLabel={`Remove ${label.toLowerCase()}`}
          >
            {`${label} ${k === 'date' ? nightLabel(String(scope[k])) : String(scope[k])}`}
          </Chip>
        ))}
        {!isEmpty(scope) && (
          <Button
            size="sm"
            variant="ghost"
            onClick={() => {
              window.clearTimeout(timer.current)
              setText('')
              onChange({})
            }}
          >
            Clear
          </Button>
        )}
      </div>
    </div>
  )
}
