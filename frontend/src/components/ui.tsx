// Design-system primitives (brand guidelines section 08): outlined buttons, tabs with an accent underline,
// readout cards with monospaced tabular figures, labels, tables, empty and error states.
import * as RadixTabs from '@radix-ui/react-tabs'
import { useEffect, useState, type ButtonHTMLAttributes, type ReactNode } from 'react'
import s from './ui.module.css'

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & { variant?: 'default' | 'primary' | 'danger' }

export function Button({ variant = 'default', className, ...rest }: ButtonProps) {
  const v = variant === 'primary' ? s.primary : variant === 'danger' ? s.danger : ''
  return <button type="button" className={[s.button, v, className].filter(Boolean).join(' ')} {...rest} />
}

export function Label({ children }: { children: ReactNode }) {
  return <div className="label">{children}</div>
}

export function ReadoutCard(props: { label: string; value: ReactNode; unit?: string; detail?: ReactNode }) {
  return (
    <section className={s.card} aria-label={props.label}>
      <Label>{props.label}</Label>
      <div className={s.readoutValue}>
        {props.value}
        {props.unit && <span className={s.readoutUnit}>{props.unit}</span>}
      </div>
      {props.detail && (
        <div className="muted" style={{ fontSize: 13 }}>
          {props.detail}
        </div>
      )}
    </section>
  )
}

export function Card({ children }: { children: ReactNode }) {
  return <section className={s.card}>{children}</section>
}

export const Tabs = RadixTabs.Root
export function TabsList({ children, label }: { children: ReactNode; label: string }) {
  return (
    <RadixTabs.List className={s.tabsList} aria-label={label}>
      {children}
    </RadixTabs.List>
  )
}
export function Tab({ value, children }: { value: string; children: ReactNode }) {
  return (
    <RadixTabs.Trigger className={s.tabsTrigger} value={value}>
      {children}
    </RadixTabs.Trigger>
  )
}
export const TabPanel = RadixTabs.Content

export function Table({ children, label }: { children: ReactNode; label: string }) {
  return (
    <table className={s.table} aria-label={label}>
      {children}
    </table>
  )
}

export function EmptyState({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className={s.state}>
      <h3>{title}</h3>
      <div className="muted">{children}</div>
    </section>
  )
}

export function ErrorState(props: { title: string; children: ReactNode; onRetry?: () => void }) {
  return (
    <section className={`${s.state} ${s.error}`} role="alert">
      <h3>{props.title}</h3>
      <div className="muted">{props.children}</div>
      {props.onRetry && (
        <p>
          <Button onClick={props.onRetry}>Retry</Button>
        </p>
      )}
    </section>
  )
}

/** A destructive action asks in the page, not in a browser dialog (007-DR-16): the button turns into the
 * question with the confirming action and Cancel. Escape cancels. */
export function ConfirmButton({
  children,
  question,
  confirm,
  onConfirm,
  className,
}: {
  children: ReactNode
  question: ReactNode
  confirm: string
  onConfirm: () => void
  className?: string
}) {
  const [asking, setAsking] = useState(false)
  useEffect(() => {
    if (!asking) return
    const esc = (e: KeyboardEvent) => e.key === 'Escape' && setAsking(false)
    document.addEventListener('keydown', esc)
    return () => document.removeEventListener('keydown', esc)
  }, [asking])
  if (!asking)
    return (
      <button
        type="button"
        className={className ?? s.button}
        onClick={(e) => {
          e.stopPropagation() // inside a clickable row, asking mustn't also open the row
          setAsking(true)
        }}
      >
        {children}
      </button>
    )
  return (
    <span className={s.confirm} role="group" aria-label="Confirm">
      <span>{question}</span>
      <Button
        variant="danger"
        onClick={(e) => {
          e.stopPropagation()
          setAsking(false)
          onConfirm()
        }}
      >
        {confirm}
      </Button>
      <Button
        onClick={(e) => {
          e.stopPropagation()
          setAsking(false)
        }}
      >
        Cancel
      </Button>
    </span>
  )
}

/** A small spinner for anything waiting on the server (owner 2026-10-11: loading must be obvious). */
export function Spinner({ label = 'Loading' }: { label?: string }) {
  return <span className={s.spinner} role="status" aria-label={label} />
}

/** A grey placeholder the size of what's coming, so the page doesn't jump when it arrives. */
export function Skeleton({
  width = '100%',
  height = 16,
}: {
  width?: number | string
  height?: number | string
}) {
  return <span className={s.skeleton} style={{ width, height }} aria-hidden="true" />
}

/** A page waiting for its first answer: a title bar and two blocks where the content will be. */
export function PageLoading() {
  return (
    <div className={s.pageLoading} aria-busy="true" aria-label="Loading">
      <Skeleton width={240} height={30} />
      <Skeleton height={120} />
      <Skeleton height={260} />
    </div>
  )
}
