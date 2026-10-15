// The scope in the current page's address (spec 018 FR-004): read it, and change it in place (the page's own
// search keys kept, the browser history not grown by every pick).
import { useNavigate, useSearch } from '@tanstack/react-router'
import { readScope, replaceScope, type Scope } from './scope'

export function useScope(): [Scope, (next: Scope) => void] {
  const search = useSearch({ strict: false }) as Record<string, unknown>
  const navigate = useNavigate()
  const scope = readScope(search)
  const setScope = (next: Scope) =>
    void navigate({
      to: '.',
      search: ((prev: Record<string, unknown>) => replaceScope(prev, next)) as never,
      replace: true,
    })
  return [scope, setScope]
}
