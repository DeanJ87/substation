// The one confirm for putting something away (006-DR-40): always three short lines — what happens to the files, to
// the records, to links and goals — and how to undo it. A refusal says why, and the confirm button stays disabled.
import { useId, type ReactNode } from 'react'
import { VERBS, type Verb } from '../features/changes/putAway'
import { Modal } from './Modal'
import { Button, Spinner } from './ui'
import s from './PutAway.module.css'

export type Impact = {
  /** Overrides the verb's files sentence (an archive's count, or a file that goes for good). */
  files?: ReactNode
  records: ReactNode
  links: ReactNode
  /** Overrides the verb's undo sentence. */
  undo?: ReactNode
}

export function PutAwayConfirm({
  verb,
  name,
  impact,
  refused,
  warning,
  busy,
  children,
  confirmLabel,
  onConfirm,
  onClose,
}: {
  verb: Verb
  /** What's being put away, as the owner knows it: "collection M31", "2025–26 · widefield". */
  name: string
  /** Null while it's being worked out. */
  impact: Impact | null
  /** Why it can't be done now; the confirm is disabled. */
  refused?: ReactNode
  /** Something to know before going ahead (e.g. the renderer loses the link). */
  warning?: ReactNode
  busy?: boolean
  /** Extra actions under a refusal (a link to what blocks it). */
  children?: ReactNode
  confirmLabel?: string
  onConfirm: () => void
  onClose: () => void
}) {
  const words = VERBS[verb]
  const title = `${words.label} ${name}?`
  const why = useId()
  const danger = verb === 'delete' || verb === 'bin'
  return (
    <Modal label={title} onClose={onClose} size="sm">
      <div className={s.box}>
        <h2 className={s.title}>{title}</h2>
        {!impact ? (
          <Spinner label="Working out what this touches" />
        ) : (
          <dl className={s.lines}>
            <div>
              <dt>Files</dt>
              <dd>{impact.files ?? words.files}</dd>
            </div>
            <div>
              <dt>Records</dt>
              <dd>{impact.records}</dd>
            </div>
            <div>
              <dt>Links and goals</dt>
              <dd>{impact.links}</dd>
            </div>
            <div className={s.undo}>
              <dt>Undo</dt>
              <dd>{impact.undo ?? words.undo}</dd>
            </div>
          </dl>
        )}
        {warning && !refused && <p className={s.warning}>{warning}</p>}
        {refused && (
          <div className={s.refused} role="alert" id={why}>
            <p>{refused}</p>
            {children}
          </div>
        )}
        <div className={s.actions}>
          <Button
            variant={danger ? 'danger' : 'primary'}
            disabled={!impact || !!refused || busy}
            aria-describedby={refused ? why : undefined}
            onClick={onConfirm}
          >
            {confirmLabel ?? words.label}
          </Button>
          <Button onClick={onClose}>Cancel</Button>
        </div>
      </div>
    </Modal>
  )
}
