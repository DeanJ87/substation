// Every value with its source (constitution II; T078), any header vs pattern disagreement, and corrections.
// A correction is stored for this content, so it applies to every copy and to identical files found later.
import { useState } from 'react'
import { Collapsible } from '../../components/Collapsible'
import { Button } from '../../components/ui'
import type { Frame } from '../datasets/queries'
import { FIELDS, FIELD_LABEL, FRAME_TYPES, useSetMetadata } from '../metadata/queries'
import s from './frames.module.css'

type Meta = Frame['metadata'][number]

export function sourceText(m: Meta): string {
  switch (m.source) {
    case 'header':
      return `from header ${m.source_detail ?? ''}`.trim()
    case 'folder_pattern':
      return `from folder ${m.source_detail ?? 'pattern'}`
    case 'filename_pattern':
      return `from file name ${m.source_detail ?? 'pattern'}`
    case 'user':
      return `set by ${m.set_by ?? 'a user'} on ${new Date(m.at).toLocaleDateString('en-GB', { day: 'numeric', month: 'short' })}`
    case 'inferred':
      return `inferred${m.source_detail ? ` (${m.source_detail})` : ''}`
    case 'settings':
      return 'from settings'
    default:
      return m.source
  }
}

function conflictText(values: Record<string, string | null>): string {
  return Object.entries(values)
    .map(([k, v]) => {
      const [src, detail] = k.split(':')
      const where =
        src === 'header'
          ? `header ${detail}`
          : src.endsWith('pattern')
            ? `${src === 'folder_pattern' ? 'folder' : 'file name'} ${detail}`
            : src
      return `${where} says ${v}`
    })
    .join('; ')
}

export function FrameValues({ frame }: { frame: Frame }) {
  const setMeta = useSetMetadata(`frame-${frame.sha256}`)
  const [editing, setEditing] = useState<string | null>(null)
  const [value, setValue] = useState('')
  const [adding, setAdding] = useState('')
  const winners = frame.metadata.filter((m) => m.is_winner)
  const have = new Set(winners.map((m) => m.field))
  const conflicts = frame.conflicts
  const missing = FIELDS.filter((f) => !have.has(f.field))

  function save(field: string, v: string | null) {
    // the value shows at once; repeated saves on this sub run in order
    setMeta.mutate({ sha256s: [frame.sha256], field, value: v })
    setEditing(null)
    setAdding('')
    setValue('')
  }

  function editor(field: string) {
    return (
      <form
        className={s.inlineEdit}
        onSubmit={(e) => {
          e.preventDefault()
          if (value.trim()) save(field, value.trim())
        }}
      >
        {field === 'frame_type' ? (
          <select aria-label={FIELD_LABEL[field]} value={value} onChange={(e) => setValue(e.target.value)}>
            <option value="">Choose…</option>
            {FRAME_TYPES.map(([v, label]) => (
              <option key={v} value={v}>
                {label}
              </option>
            ))}
          </select>
        ) : (
          <input
            aria-label={FIELD_LABEL[field] ?? field}
            value={value}
            onChange={(e) => setValue(e.target.value)}
            className="mono"
          />
        )}
        <Button type="submit" variant="primary" disabled={!value.trim()}>
          Save
        </Button>
        <Button type="button" onClick={() => setEditing(null)}>
          Cancel
        </Button>
      </form>
    )
  }

  return (
    <Collapsible id="frame-values" title="Values">
      <table className={s.kv}>
        <tbody>
          {winners.map((m) => (
            <tr key={`${m.field}-${m.source}-${m.source_detail}`}>
              <th scope="row" className="label">
                {FIELD_LABEL[m.field] ?? m.field.replace('_', ' ')}
              </th>
              <td className="mono">{editing === m.field ? editor(m.field) : (m.value ?? '—')}</td>
              <td className="muted">{sourceText(m)}</td>
              <td className={s.fieldActions}>
                <span>
                  {editing !== m.field && FIELD_LABEL[m.field] && (
                    <button
                      className={s.link}
                      onClick={() => {
                        setEditing(m.field)
                        setValue(m.field === 'frame_type' ? frame.frame_type : (m.value ?? ''))
                      }}
                    >
                      {m.field === 'frame_type' ? 'Change type' : 'Correct'}
                    </button>
                  )}
                  {m.source === 'user' && editing !== m.field && (
                    <button className={s.link} onClick={() => save(m.field, null)}>
                      Undo
                    </button>
                  )}
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {conflicts.length > 0 && (
        <div className={s.conflicts}>
          <h4>Sources disagree</h4>
          <ul className={s.plain}>
            {conflicts.map((c) => (
              <li key={c.field}>
                <strong>{FIELD_LABEL[c.field] ?? c.field}:</strong> {conflictText(c.values)}.
              </li>
            ))}
          </ul>
        </div>
      )}
      {missing.length > 0 && (
        <div className={s.addValue}>
          {adding ? (
            editor(adding)
          ) : (
            <select
              aria-label="Set a missing value"
              value=""
              onChange={(e) => {
                setAdding(e.target.value)
                setValue('')
              }}
            >
              <option value="">Set a missing value…</option>
              {missing.map((f) => (
                <option key={f.field} value={f.field}>
                  {f.label}
                </option>
              ))}
            </select>
          )}
        </div>
      )}
    </Collapsible>
  )
}
