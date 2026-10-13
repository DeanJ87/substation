// A thin bar along the top while the page waits on the server (owner 2026-10-11). Counts first loads, changed filters (a query with nothing to show yet) and saves; background polling
// doesn't count, so it isn't always on.
import { useIsFetching, useIsMutating } from '@tanstack/react-query'
import { useEffect, useState } from 'react'
import s from './Busy.module.css'

export function BusyBar() {
  const loading = useIsFetching({ predicate: (q) => q.state.data === undefined || q.state.isInvalidated })
  const saving = useIsMutating()
  const busy = loading + saving > 0
  // only after a moment, so quick answers don't flash
  const [shown, setShown] = useState(false)
  useEffect(() => {
    if (!busy) return
    const t = setTimeout(() => setShown(true), 200)
    return () => {
      clearTimeout(t)
      setShown(false)
    }
  }, [busy])
  return busy && shown ? <div className={s.bar} role="progressbar" aria-label="Loading" /> : null
}
