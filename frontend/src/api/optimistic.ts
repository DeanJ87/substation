// Actions change the screen at once and the server confirms afterwards (owner 2026-10-11). A mutation lists the cached
// queries it changes and how; they are patched before the request, rolled back if it fails (with a toast), and
// refreshed from the server when it settles either way.
import type { QueryClient, QueryKey } from '@tanstack/react-query'

/** One cached query and how this action changes it. The updater gets the cached value (possibly undefined) and
 * returns the new one; leave it alone by returning it unchanged. */
export type Patch = [QueryKey, (old: unknown) => unknown]

type Snapshot = [QueryKey, unknown][]

/** onMutate / onError / onSettled for useMutation. `patches` may match several queries by prefix (every
 * ['subs', id] page, say); `refresh` lists extra keys to refetch once the server has answered. */
export function optimistic<V>(
  qc: QueryClient,
  patches: (vars: V) => Patch[],
  refresh: (vars: V) => QueryKey[] = () => [],
) {
  return {
    onMutate: async (vars: V): Promise<{ snapshot: Snapshot }> => {
      const ps = patches(vars)
      // stop a poll landing mid-change and overwriting the optimistic value
      await Promise.all(ps.map(([key]) => qc.cancelQueries({ queryKey: key })))
      const snapshot: Snapshot = []
      for (const [key, update] of ps)
        for (const [k, old] of qc.getQueriesData({ queryKey: key })) {
          snapshot.push([k, old])
          qc.setQueryData(k, update(old))
        }
      return { snapshot }
    },
    onError: (_e: Error, _vars: V, ctx: { snapshot: Snapshot } | undefined) => {
      for (const [k, old] of ctx?.snapshot ?? []) qc.setQueryData(k, old)
    },
    onSettled: (_d: unknown, _e: Error | null, vars: V) => {
      for (const [key] of patches(vars)) void qc.invalidateQueries({ queryKey: key })
      for (const key of refresh(vars)) void qc.invalidateQueries({ queryKey: key })
    },
  }
}

/** Patch the items of a list (or of every page of an infinite list) that match. */
export function patchItems<T>(old: unknown, match: (x: T) => boolean, change: (x: T) => T | null): unknown {
  const fix = (xs: T[]) => xs.flatMap((x) => (match(x) ? (change(x) ?? []) : [x]))
  if (Array.isArray(old)) return fix(old as T[])
  const inf = old as { pages?: T[][] } | undefined
  if (inf?.pages) return { ...inf, pages: inf.pages.map(fix) }
  return old
}

/** Patch every object anywhere in a cached value that matches: for answers whose shape nests the same item in
 * several places (a sub in a session group in a review list). Unchanged branches keep their identity. */
export function patchDeep(
  old: unknown,
  match: (x: Record<string, unknown>) => boolean,
  change: (x: Record<string, unknown>) => Record<string, unknown>,
): unknown {
  if (Array.isArray(old)) {
    let changed = false
    const out = old.map((x) => {
      const y = patchDeep(x, match, change)
      if (y !== x) changed = true
      return y
    })
    return changed ? out : old
  }
  if (old && typeof old === 'object') {
    const o = old as Record<string, unknown>
    if (match(o)) return change(o)
    let changed = false
    const out: Record<string, unknown> = {}
    for (const [k, v] of Object.entries(o)) {
      const y = patchDeep(v, match, change)
      if (y !== v) changed = true
      out[k] = y
    }
    return changed ? out : old
  }
  return old
}
