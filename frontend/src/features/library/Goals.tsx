// Integration goals (spec 019): hours of usable integration wanted per filter, and how far along each is.
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { api, unwrap } from '../../api/client'
import type { components } from '../../api/schema'
import { Collapsible } from '../../components/Collapsible'
import { Button } from '../../components/ui'
import { integrationText } from '../format'
import v from '../v2/v2.module.css'
import s from './library.module.css'
import g from './goals.module.css'

type Card = components['schemas']['CollectionCard']

export function goalProgress(card: Card, f: string) {
  const t = card.filter_time?.[f]
  const kept = t?.accepted_s ?? card.filters[f] ?? 0
  const waiting = t ? Math.max(0, t.total_s - t.accepted_s - t.rejected_s) : 0
  const goal = (card.goals?.[f] ?? 0) * 3600
  return { kept, waiting, goal, pct: goal ? Math.min(100, Math.round((kept / goal) * 100)) : null }
}

export function Goals({ card }: { card: Card }) {
  const qc = useQueryClient()
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState<Record<string, string>>({})
  const [newFilter, setNewFilter] = useState('')
  const save = useMutation({
    mutationFn: async (goals: Record<string, number | null>) =>
      unwrap(await api.PATCH('/collections/{id}', { params: { path: { id: card.id } }, body: { goals } })),
    onSuccess: () => setEditing(false),
    onSettled: () => void qc.invalidateQueries(),
    meta: { failed: "Couldn't save the goals" },
  })
  const filters = [...new Set([...Object.keys(card.filters), ...Object.keys(card.goals ?? {})])].sort()
  const set = Object.keys(card.goals ?? {}).length
  const start = () => {
    setDraft(Object.fromEntries(filters.map((f) => [f, card.goals?.[f] ? String(card.goals[f]) : ''])))
    setNewFilter('')
    setEditing(true)
  }
  const submit = () => {
    const goals: Record<string, number | null> = {}
    for (const [f, h] of Object.entries(draft)) goals[f] = h.trim() ? Number(h) : null
    save.mutate(goals)
  }
  return (
    <section className={`${v.card} ${v.cardPad}`}>
      <Collapsible
        id="collection-goals"
        title="Goals"
        meta={set ? `${set} filter${set === 1 ? '' : 's'}` : 'none set'}
      >
        {!editing && !set && (
          <p className="muted">
            Set the hours of usable integration you want per filter, to see how far along each is.
          </p>
        )}
        {!editing && set > 0 && (
          <ul className={g.list}>
            {filters
              .filter((f) => card.goals?.[f])
              .map((f) => {
                const p = goalProgress(card, f)
                const pct = (x: number) => `${Math.min(100, (x / p.goal) * 100)}%`
                return (
                  <li key={f} className={g.row}>
                    <strong>{f}</strong>
                    <span
                      className={`${s.bar} ${g.bar}`}
                      role="progressbar"
                      aria-label={`${f} goal`}
                      aria-valuemin={0}
                      aria-valuemax={100}
                      aria-valuenow={p.pct ?? 0}
                    >
                      <span className={s.barOk} style={{ width: pct(p.kept) }} />
                      <span
                        className={s.barWait}
                        style={{ width: pct(Math.min(p.waiting, Math.max(0, p.goal - p.kept))) }}
                      />
                    </span>
                    <span className={v.mono}>
                      <span className={p.kept >= p.goal ? v.ok : v.accent}>{integrationText(p.kept)}</span> of{' '}
                      {integrationText(p.goal)} · {p.pct}%
                      {p.kept < p.goal && (
                        <span className={v.muted}> · {integrationText(p.goal - p.kept)} to go</span>
                      )}
                      {p.waiting > 0 && (
                        <span className={v.muted}> · {integrationText(p.waiting)} waiting</span>
                      )}
                    </span>
                  </li>
                )
              })}
          </ul>
        )}
        {editing ? (
          <form
            className={g.form}
            onSubmit={(e) => {
              e.preventDefault()
              submit()
            }}
          >
            {Object.keys(draft).map((f) => (
              <label key={f} className={g.field}>
                <span>{f}</span>
                <input
                  type="number"
                  min={0}
                  max={1000}
                  step={0.5}
                  inputMode="decimal"
                  placeholder="hours"
                  value={draft[f]}
                  onChange={(e) => setDraft({ ...draft, [f]: e.target.value })}
                />
                <span className="muted">h</span>
              </label>
            ))}
            <span className={g.field}>
              <input
                aria-label="Another filter"
                placeholder="Another filter"
                value={newFilter}
                onChange={(e) => setNewFilter(e.target.value)}
              />
              <Button
                type="button"
                disabled={!newFilter.trim() || newFilter.trim() in draft}
                onClick={() => {
                  setDraft({ ...draft, [newFilter.trim()]: '' })
                  setNewFilter('')
                }}
              >
                Add
              </Button>
            </span>
            <span className={v.actions}>
              <Button variant="primary" type="submit" disabled={save.isPending}>
                Save goals
              </Button>
              <Button type="button" onClick={() => setEditing(false)}>
                Cancel
              </Button>
            </span>
          </form>
        ) : (
          <Button onClick={start}>{set ? 'Change goals' : 'Set goals'}</Button>
        )}
      </Collapsible>
    </section>
  )
}
