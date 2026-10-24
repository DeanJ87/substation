// Which post-processing steps one run takes (010-DR-29): each available step on or off, starting from Settings →
// Processing's selection. The steps keep Settings' parameters; automatic runs keep Settings' selection.
import { useState } from 'react'
import type { components } from '../../api/schema'
import { Modal } from '../../components/Modal'
import { Button } from '../../components/ui'
import v from '../v2/v2.module.css'
import s from './post.module.css'

export type StepChoice = components['schemas']['PostStepChoice']

export function PostRunDialog({
  name,
  steps,
  again,
  onRun,
  onClose,
}: {
  name: string
  steps: StepChoice[]
  again: boolean
  onRun: (steps: string[]) => void
  onClose: () => void
}) {
  const [on, setOn] = useState<string[]>(steps.filter((x) => x.on && x.available).map((x) => x.step))
  const n = on.length
  return (
    <Modal label={`Post-process ${name}`} onClose={onClose} size="sm">
      <form
        className={s.dialog}
        onSubmit={(e) => {
          e.preventDefault()
          if (!n) return
          onRun(steps.map((x) => x.step).filter((x) => on.includes(x)))
          onClose()
        }}
      >
        <h2 className={s.title}>{again ? 'Post-process again' : 'Post-process'}</h2>
        <p className={v.muted}>
          {name}, from the untouched file. Each step works on the one before, with its settings from Settings
          → Processing.
        </p>
        <fieldset className={s.steps}>
          <legend className={s.legend}>Steps for this run</legend>
          {steps.map((x) => (
            <label key={x.step} className={s.step} data-off={!x.available || undefined}>
              <input
                type="checkbox"
                checked={on.includes(x.step)}
                disabled={!x.available}
                onChange={(e) => setOn(e.target.checked ? [...on, x.step] : on.filter((k) => k !== x.step))}
              />
              <span className={s.stepText}>
                {x.label}
                <span className={v.muted}>
                  {x.available ? x.tool : x.reason || `${x.tool} isn't available on the finisher.`}
                  {x.available && !x.on ? ' · off in Settings' : ''}
                </span>
              </span>
            </label>
          ))}
        </fieldset>
        <div className={v.actions}>
          <Button type="submit" variant="primary" disabled={!n}>
            {n ? `Run ${n} step${n === 1 ? '' : 's'}` : 'Choose a step'}
          </Button>
          <Button type="button" onClick={onClose}>
            Cancel
          </Button>
        </div>
      </form>
    </Modal>
  )
}
