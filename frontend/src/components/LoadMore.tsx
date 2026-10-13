// The end of a long list: asks for the next page as it scrolls into view (owner 2026-10-11: long lists load as you
// scroll, inside their own section).
import { useEffect, useRef } from 'react'
import { Spinner } from './ui'

export function LoadMore({
  hasMore,
  loading,
  onMore,
}: {
  hasMore: boolean
  loading: boolean
  onMore: () => void
}) {
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => {
    const el = ref.current
    if (!el || !hasMore) return
    const io = new IntersectionObserver((e) => e[0]?.isIntersecting && !loading && onMore(), {
      rootMargin: '200px',
    })
    io.observe(el)
    return () => io.disconnect()
  }, [hasMore, loading, onMore])
  if (!hasMore && !loading) return null
  return (
    <div ref={ref} style={{ padding: 12, display: 'flex', justifyContent: 'center' }} aria-live="polite">
      {loading && <Spinner label="Loading more" />}
    </div>
  )
}
