// Stitch mosaic or Stack together for chosen filters (004-DR-34): pick the filters, see which masters go into
// each (an older master used as it is is marked), then start. Laid out like a dataset's New master builder.
import { useState } from 'react'
import type { components } from '../../api/schema'
import { Modal } from '../../components/Modal'
import { compareFilters, filterName } from '../../components/filters'
import { Button, FilterTag, Tag } from '../../components/ui'
import { integrationText, plural } from '../format'
import v from '../v2/v2.module.css'
import c from './collection.module.css'
import { METHOD, type Method } from './Projects'

type Plan = components['schemas']['CombinedPlanOut']

export function CombineDialog({
  plan,
  method,
  projectName,
  onStart,
  onClose,
}: {
  plan: Plan
  method: Method
  projectName: string | null
  onStart: (filters: string[]) => void
  onClose: () => void
}) {
  const filters = Object.entries(plan.filters).sort(([a], [b]) => compareFilters(a, b))
  const [picked, setPicked] = useState<string[]>(filters.map(([f]) => f))
  const stitch = method === 'stitch'
  const n = picked.length
  const verb = stitch ? 'Stitch' : 'Stack'
  const title = `${METHOD[method].label}${projectName ? ` · ${projectName}` : ''}`
  return (
    <Modal label={title} onClose={onClose} size="md">
      <form
        className={c.dialog}
        onSubmit={(e) => {
          e.preventDefault()
          if (!n) return
          onStart(filters.map(([f]) => f).filter((f) => picked.includes(f)))
          onClose()
        }}
      >
        <h2 className={c.dialogTitle}>{title}</h2>
        <p className={v.muted}>
          {stitch
            ? `Each chosen filter's panels placed on one canvas by their plate solutions. The canvas is drawn from every panel of every filter, so a filter stitched later lines up pixel for pixel.`
            : `Each chosen filter's masters of one field stacked into a deeper one, weighted by their subs, aligned to ${plan.reference_label}.`}
        </p>
        <fieldset className={c.combineFilters}>
          <legend className={c.combineLegend}>Filters</legend>
          {filters.map(([f, inputs]) => {
            const on = picked.includes(f)
            const total = inputs.reduce((t, x) => t + (x.integration_s ?? 0), 0)
            return (
              <div key={f} className={c.combineFilter} data-off={!on || undefined}>
                <label className={c.combineHead}>
                  <input
                    type="checkbox"
                    checked={on}
                    onChange={(e) =>
                      setPicked(e.target.checked ? [...picked, f] : picked.filter((x) => x !== f))
                    }
                  />
                  <FilterTag filter={f} />
                  <span className={v.muted}>
                    {plural(inputs.length, stitch ? 'panel master' : 'master')} · {integrationText(total)}
                  </span>
                </label>
                <ul className={c.combineInputs} aria-label={`${filterName(f)} masters`}>
                  {inputs.map((x) => (
                    <li key={x.master}>
                      <span>
                        {x.label}
                        {x.version ? ` · v${x.version}` : ''}
                      </span>
                      <span className={v.muted}>
                        {x.integration_s ? integrationText(x.integration_s) : ''}
                        {x.subs ? ` · ${plural(x.subs, 'sub')}` : ''}
                      </span>
                      {x.stale && (
                        <Tag tone="warn" title="Newer subs since: used as it is, not stacked again">
                          Older master
                        </Tag>
                      )}
                    </li>
                  ))}
                </ul>
              </div>
            )
          })}
        </fieldset>
        {plan.left_out.length > 0 && <p className={v.muted}>Left out: {plan.left_out.join('; ')}.</p>}
        <div className={v.actions}>
          <Button type="submit" variant="primary" disabled={!n}>
            {n === 0
              ? 'Choose a filter'
              : n === 1
                ? `${verb} ${filterName(picked[0])}`
                : `${verb} ${n} filters`}
          </Button>
          <Button type="button" onClick={onClose}>
            Cancel
          </Button>
        </div>
      </form>
    </Modal>
  )
}
