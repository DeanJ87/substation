// Short notes in the corner: chiefly an action that didn't save, so its instant change was undone (owner
// 2026-10-11). Any failed mutation shows one; `meta.failed` names the action ("Couldn't reject the sub").
import { useEffect, useState } from 'react'
import s from './Toasts.module.css'

type Toast = { id: number; text: string; bad: boolean }
let next = 1
let listeners: ((t: Toast[]) => void)[] = []
let toasts: Toast[] = []

function emit() {
  for (const l of listeners) l(toasts)
}

export function toast(text: string, bad = false) {
  // the same message twice (a spammed button) shows once
  if (toasts.some((t) => t.text === text)) return
  const t = { id: next++, text, bad }
  toasts = [...toasts, t].slice(-4)
  emit()
  setTimeout(
    () => {
      toasts = toasts.filter((x) => x.id !== t.id)
      emit()
    },
    bad ? 7000 : 3500,
  )
}

export function Toasts() {
  const [list, setList] = useState<Toast[]>(toasts)
  useEffect(() => {
    listeners.push(setList)
    return () => {
      listeners = listeners.filter((l) => l !== setList)
    }
  }, [])
  return (
    <div className={s.stack} aria-live="polite">
      {list.map((t) => (
        <div key={t.id} className={`${s.toast} ${t.bad ? s.bad : ''}`} role={t.bad ? 'alert' : 'status'}>
          {t.text}
        </div>
      ))}
    </div>
  )
}
