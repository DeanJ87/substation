// The shared filter bar (spec 018): rig, filter and nights, written to the address so the page, its requests and
// its links all carry the same scope.
import { useQuery } from '@tanstack/react-query'
import { api, unwrap } from '../../api/client'
import { Button } from '../../components/ui'
import { isEmpty, type Scope } from './scope'
import s from './scope.module.css'

export function ScopeBar({
  scope,
  onChange,
  filters = [],
}: {
  scope: Scope
  onChange: (next: Scope) => void
  filters?: string[]
}) {
  const rigs = useQuery({ queryKey: ['rigs'], queryFn: async () => unwrap(await api.GET('/rigs')) })
  const set = (patch: Partial<Scope>) => onChange({ ...scope, ...patch })
  return (
    <div className={s.bar} role="group" aria-label="Filters">
      <select
        aria-label="Rig"
        value={scope.rig ?? ''}
        onChange={(e) => set({ rig: e.target.value ? Number(e.target.value) : undefined })}
      >
        <option value="">Rig: All</option>
        {(rigs.data ?? []).map((r) => (
          <option key={r.id} value={r.id}>
            {r.name}
          </option>
        ))}
      </select>
      <select
        aria-label="Filter"
        value={scope.filter ?? ''}
        onChange={(e) => set({ filter: e.target.value || undefined })}
      >
        <option value="">Filter: All</option>
        {[...new Set([...filters, ...(scope.filter ? [scope.filter] : [])])].sort().map((f) => (
          <option key={f}>{f}</option>
        ))}
      </select>
      <label>
        From{' '}
        <input
          type="date"
          value={scope.date_from ?? ''}
          max={scope.date_to}
          onChange={(e) => set({ date_from: e.target.value || undefined })}
        />
      </label>
      <label>
        To{' '}
        <input
          type="date"
          value={scope.date_to ?? ''}
          min={scope.date_from}
          onChange={(e) => set({ date_to: e.target.value || undefined })}
        />
      </label>
      {!isEmpty(scope) && <Button onClick={() => onChange({})}>Clear</Button>}
    </div>
  )
}
