// A long list already in memory, shown a slice at a time and grown as its end scrolls into view (owner
// 2026-10-11: enormous lists lazy-load). Pair with <LoadMore>. The slice resets when the list's identity changes
// (a new filter), not on every poll.
import { useCallback, useState } from 'react'

export function useProgressive<T>(items: readonly T[], step = 60, resetKey: unknown = null) {
  const [state, setState] = useState({ key: resetKey, shown: step })
  // a new filter starts again from the top
  const shown = state.key === resetKey ? state.shown : step
  if (state.key !== resetKey) setState({ key: resetKey, shown: step })
  const more = useCallback(() => setState((s) => ({ ...s, shown: s.shown + step })), [step])
  return { visible: items.slice(0, shown), hasMore: items.length > shown, more }
}
