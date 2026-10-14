// Review is a filter now (spec 012): /review opens the dataset with the most flagged subs, showing only those, with
// the viewer on the first. /review?dataset=N opens that dataset's flagged subs.
import { getRouteApi, useNavigate } from '@tanstack/react-router'
import { useEffect } from 'react'
import { EmptyState, PageLoading } from '../../components/ui'
import { useReview } from '../v2/hooks'

const route = getRouteApi('/app/review')

export function ReviewScreen() {
  const { dataset } = route.useSearch()
  const q = useReview()
  const navigate = useNavigate()
  const groups = q.data ?? []
  const per = new Map<number, { n: number; first: string }>()
  for (const g of groups) {
    const cur = per.get(g.dataset_id) ?? { n: 0, first: g.subs[0]?.sha256 ?? '' }
    per.set(g.dataset_id, { n: cur.n + g.subs.length, first: cur.first || g.subs[0]?.sha256 || '' })
  }
  const target =
    dataset != null && per.has(dataset) ? dataset : [...per.entries()].sort((a, b) => b[1].n - a[1].n)[0]?.[0]
  useEffect(() => {
    if (target == null) return
    void navigate({
      to: '/datasets/$id',
      params: { id: String(target) },
      search: { tab: 'subs', show: 'flagged', sub: per.get(target)?.first || undefined },
      replace: true,
    })
  })
  if (q.isSuccess && target == null)
    return <EmptyState title="Nothing to review">No subs are flagged.</EmptyState>
  return <PageLoading />
}
