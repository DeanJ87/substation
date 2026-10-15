// Several datasets at once (spec 016 U6): re-grade, stack with the default rule, or move to another collection
// (Undo in the toast, Ctrl/Cmd+Z, or Activity → Your changes).
import { useState } from 'react'
import { BulkBar } from '../../components/BulkBar'
import { Button, ConfirmButton } from '../../components/ui'
import ui from '../../components/ui.module.css'
import { useBulkDatasets } from '../changes/bulk'
import { useLibrary } from '../v2/hooks'
import v from '../v2/v2.module.css'

export function DatasetBulkBar({
  chosen,
  onClear,
  shown,
  onChooseShown,
  from,
}: {
  chosen: Set<number>
  onClear: () => void
  shown: number
  onChooseShown: () => void
  from: number | null // the collection they're shown in; null for datasets not in one
}) {
  const act = useBulkDatasets()
  const lib = useLibrary()
  const [to, setTo] = useState('')
  const ids = [...chosen]
  const n = chosen.size
  const others = (lib.data?.collections ?? []).filter((c) => c.id !== from)
  const target = others.find((c) => String(c.id) === to)
  const move = () => {
    const collection_id = to === 'out' ? null : Number(to)
    act.move.mutate(
      { dataset_ids: ids, collection_id, name: target?.name },
      {
        onSuccess: () => {
          setTo('')
          onClear()
        },
      },
    )
  }
  return (
    <BulkBar count={n} noun={['dataset', 'datasets']} label="Selected datasets" onClear={onClear} inset>
      <Button
        disabled={act.regrade.isPending}
        onClick={() => act.regrade.mutate(ids, { onSuccess: onClear })}
      >
        Re-grade
      </Button>
      <ConfirmButton
        className={ui.button}
        question={
          <>Start a master for each of the {n} with accepted and down-weighted subs from every night?</>
        }
        confirm={`Stack ${n}`}
        onConfirm={() => act.stack.mutate(ids, { onSuccess: onClear })}
      >
        Stack
      </ConfirmButton>
      <select className={v.select} value={to} onChange={(e) => setTo(e.target.value)} aria-label="Move to">
        <option value="">Move to…</option>
        {from !== null && <option value="out">Out of this collection</option>}
        {others.map((c) => (
          <option key={c.id} value={c.id}>
            {c.name}
          </option>
        ))}
      </select>
      <Button variant="primary" disabled={!to || act.move.isPending} onClick={move}>
        Move
      </Button>
      {n < shown && <Button onClick={onChooseShown}>Select all {shown.toLocaleString('en-GB')} shown</Button>}
    </BulkBar>
  )
}
