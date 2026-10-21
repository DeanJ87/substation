// An ordered list of short processing steps (spec 020, 020-FR-006), e.g. GraXpert, BlurXTerminator: edit, reorder,
// remove and add, then save the whole list. Used for one finished project and for the default in Settings.
import { useState } from 'react'
import { Button } from '../../components/ui'
import f from './finished.module.css'

export function StepList({
  steps,
  onSave,
  disabled,
  saving,
  name = 'processing steps',
}: {
  steps: string[]
  onSave: (steps: string[]) => void
  disabled: boolean
  saving?: boolean
  name?: string
}) {
  const [draft, setDraft] = useState<string[] | null>(null)
  const [adding, setAdding] = useState('')
  const cur = draft ?? steps
  const clean = cur.map((x) => x.trim()).filter(Boolean)
  const dirty = draft != null && JSON.stringify(clean) !== JSON.stringify(steps)
  const edit = (next: string[]) => setDraft(next)
  const move = (i: number, by: number) => {
    const next = [...cur]
    ;[next[i], next[i + by]] = [next[i + by], next[i]]
    edit(next)
  }
  const add = () => {
    if (!adding.trim()) return
    edit([...cur, adding.trim()])
    setAdding('')
  }
  return (
    <div className={f.steps}>
      {cur.length ? (
        <ol className={f.stepList} aria-label={name}>
          {cur.map((step, i) => (
            <li key={i} className={f.stepRow}>
              <span className={f.stepNo} aria-hidden="true">
                {i + 1}
              </span>
              <input
                className={f.input}
                value={step}
                maxLength={60}
                disabled={disabled}
                aria-label={`Step ${i + 1}`}
                onChange={(e) => edit(cur.map((x, j) => (j === i ? e.target.value : x)))}
              />
              {!disabled && (
                <span className={f.stepActions}>
                  <Button aria-label={`Move step ${i + 1} up`} disabled={i === 0} onClick={() => move(i, -1)}>
                    ↑
                  </Button>
                  <Button
                    aria-label={`Move step ${i + 1} down`}
                    disabled={i === cur.length - 1}
                    onClick={() => move(i, 1)}
                  >
                    ↓
                  </Button>
                  <Button
                    aria-label={`Remove step ${i + 1}`}
                    onClick={() => edit(cur.filter((_, j) => j !== i))}
                  >
                    Remove
                  </Button>
                </span>
              )}
            </li>
          ))}
        </ol>
      ) : (
        <p className="muted">No steps yet.</p>
      )}
      {!disabled && (
        <form
          className={f.stepAdd}
          onSubmit={(e) => {
            e.preventDefault()
            add()
          }}
        >
          <input
            className={f.input}
            value={adding}
            maxLength={60}
            placeholder="e.g. BlurXTerminator"
            aria-label="New step"
            onChange={(e) => setAdding(e.target.value)}
          />
          <Button type="submit" disabled={!adding.trim()}>
            Add step
          </Button>
        </form>
      )}
      {dirty && !disabled && (
        <div className={f.saveRow}>
          <Button variant="primary" disabled={saving} onClick={() => onSave(clean)}>
            Save steps
          </Button>
          <Button onClick={() => setDraft(null)}>Discard</Button>
        </div>
      )}
    </div>
  )
}
