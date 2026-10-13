// Bulk metadata editing (T081): set one field for every selected frame, frame type included. Stored by content,
// so it applies to every copy and to identical files found later.
import { useState } from 'react'
import { Button } from '../../components/ui'
import { FIELDS, FRAME_TYPES, useAddIgnore, useSetMetadata } from '../metadata/queries'
import s from './frames.module.css'

export function BulkEdit({ selected, onDone }: { selected: string[]; onDone: () => void }) {
  const setMeta = useSetMetadata()
  const ignore = useAddIgnore()
  const [field, setField] = useState('filter')
  const [value, setValue] = useState('')
  const n = selected.length
  if (n === 0) return null

  return (
    <form
      className={s.bulkBar}
      aria-label="Edit selected subs"
      onSubmit={(e) => {
        e.preventDefault()
        if (!value.trim()) return
        // the values change at once; the selection clears with them
        setMeta.mutate({ sha256s: selected, field, value: value.trim() })
        setValue('')
        onDone()
      }}
    >
      <strong>{n} selected</strong>
      <label>
        Set{' '}
        <select
          value={field}
          onChange={(e) => {
            setField(e.target.value)
            setValue('')
          }}
        >
          {FIELDS.map((f) => (
            <option key={f.field} value={f.field}>
              {f.label}
            </option>
          ))}
        </select>
      </label>
      <label>
        to{' '}
        {field === 'frame_type' ? (
          <select value={value} onChange={(e) => setValue(e.target.value)}>
            <option value="">Choose…</option>
            {FRAME_TYPES.map(([v, label]) => (
              <option key={v} value={v}>
                {label}
              </option>
            ))}
          </select>
        ) : (
          <input value={value} onChange={(e) => setValue(e.target.value)} className="mono" />
        )}
      </label>
      <Button type="submit" variant="primary" disabled={!value.trim()}>
        Apply to {n}
      </Button>
      <Button
        type="button"
        onClick={() => {
          ignore.mutate({
            rules: selected.map((sha) => ({ kind: 'content', value: sha })),
            sha256s: selected,
          })
          onDone()
        }}
      >
        Ignore {n === 1 ? 'it' : `all ${n}`}
      </Button>
      <Button type="button" onClick={onDone}>
        Clear selection
      </Button>
    </form>
  )
}
