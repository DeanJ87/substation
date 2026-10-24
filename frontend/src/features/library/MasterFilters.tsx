// The Masters tab narrowed to one filter (006-DR-44): a chip per filter its masters are in, canonical order, each
// with how many masters (dataset masters and stitched or stacked ones). The choice is the scope's `filter`, so it is
// kept in the address and a link can open on it.
import { useQueries } from '@tanstack/react-query'
import { api, unwrap } from '../../api/client'
import { filterKey, filterName, sortFilters } from '../../components/filters'
import { Chip, ChipGroup, FilterTag } from '../../components/ui'

type Method = 'stitch' | 'stack'

/** The stitched and stacked masters of a project (or of the whole collection): one query, shared by the
 * Masters tab's sections and its filter chips. */
export function combinedQuery(id: number, project: number | null, method: Method | null = null) {
  return {
    queryKey: method ? ['combined', id, project, method] : ['combined', id, project],
    queryFn: async () =>
      unwrap(
        await api.GET('/collections/{id}/combined', {
          params: {
            path: { id },
            query: { ...(project ? { project } : {}), ...(method ? { method } : {}) },
          },
        }),
      ),
  }
}

/** Two spellings of one filter ("Ha", "Hα") are the same filter. */
export function sameFilter(a: string | null | undefined, b: string | null | undefined): boolean {
  const ka = filterKey(a)
  const kb = filterKey(b)
  if (ka || kb) return ka === kb
  return filterName(a) === filterName(b)
}

/** Every stitched or stacked master the tab shows, across its project sections. */
export function useCombinedFilters(id: number, projects: (number | null)[], enabled: boolean): string[] {
  const qs = useQueries({
    queries: projects.map((p) => ({ ...combinedQuery(id, p), enabled })),
  })
  return qs.flatMap((q) => (q.data?.combined ?? []).filter((x) => x.id > 0).map((x) => x.filter))
}

/** How many masters there are of each filter, in canonical order; a filter the address asks for that none is in
 * shows with 0, so an empty tab says why. */
export function filterCounts(filters: string[], chosen?: string): [string, number][] {
  const counts = new Map<string, number>()
  for (const f of filters) {
    const name = filterName(f)
    if (name) counts.set(name, (counts.get(name) ?? 0) + 1)
  }
  if (chosen && ![...counts.keys()].some((k) => sameFilter(k, chosen))) counts.set(filterName(chosen), 0)
  return sortFilters([...counts.keys()]).map((f) => [f, counts.get(f) ?? 0])
}

export function MasterFilterChips({
  filters,
  chosen,
  onChoose,
}: {
  /** One entry per master shown on the tab: its filter. */
  filters: string[]
  chosen: string | undefined
  onChoose: (filter: string | undefined) => void
}) {
  const rows = filterCounts(filters, chosen)
  // one filter (or none) is nothing to choose between, unless an address asked for another
  if (rows.length < 2 && !chosen) return null
  return (
    <ChipGroup label="Show masters of one filter">
      <Chip pressed={!chosen} onClick={() => onChoose(undefined)} count={filters.length}>
        All
      </Chip>
      {rows.map(([f, n]) => (
        <Chip key={f} pressed={!!chosen && sameFilter(f, chosen)} onClick={() => onChoose(f)} count={n}>
          <FilterTag filter={f} plain />
        </Chip>
      ))}
    </ChipGroup>
  )
}
