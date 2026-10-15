// Short notes in the corner: chiefly an action that didn't save, so its instant change was undone (owner
// 2026-10-11). Any failed mutation shows one; `meta.failed` names the action ("Couldn't reject the sub").
import { useEffect, useState } from 'react'
import s from './Toasts.module.css'

// spec 016: a toast can carry one action (Undo); it then stays a little longer
export type ToastAction = { label: string; run: () => void }
type Toast = { id: number; text: string; bad: boolean; action?: ToastAction }
let next = 1
let listeners: ((t: Toast[]) => void)[] = []
let toasts: Toast[] = []

function emit() {
  for (const l of listeners) l(toasts)
}

function dismiss(id: number) {
  toasts = toasts.filter((x) => x.id !== id)
  emit()
}

export function toast(text: string, bad = false, action?: ToastAction) {
  // the same message twice (a spammed button) shows once
  if (toasts.some((t) => t.text === text)) return
  const t = { id: next++, text, bad, action }
  toasts = [...toasts, t].slice(-4)
  emit()
  setTimeout(() => dismiss(t.id), bad || action ? 8000 : 3500)
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
          <span>{t.text}</span>
          {t.action && (
            <button
              type="button"
              className={s.action}
              onClick={() => {
                dismiss(t.id)
                t.action?.run()
              }}
            >
              {t.action.label}
            </button>
          )}
        </div>
      ))}
    </div>
  )
}
