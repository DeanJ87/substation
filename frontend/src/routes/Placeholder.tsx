import { EmptyState } from '../components/ui'

export function Placeholder({ title, story }: { title: string; story: string }) {
  return <EmptyState title={title}>This screen arrives with {story}.</EmptyState>
}
