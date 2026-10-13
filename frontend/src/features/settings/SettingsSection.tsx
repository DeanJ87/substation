// One settings section that folds away (owner 2026-10-11: collapsible sections). The anchor id stays on the
// outside so /settings#workers still scrolls to it, and a link straight to a section opens it.
import { useState, type ReactNode } from 'react'
import { Collapsible } from '../../components/Collapsible'
import s from './settings.module.css'

export function SettingsSection({
  id,
  title,
  meta,
  children,
}: {
  id: string
  title: ReactNode
  meta?: ReactNode
  children: ReactNode
}) {
  // runs before the Collapsible below reads its remembered state
  useState(() => {
    if (window.location.hash !== `#${id}`) return
    try {
      localStorage.setItem(`sst.open.settings-${id}`, '1')
    } catch {
      // private window: it opens as remembered
    }
  })
  return (
    <div className={s.section} id={id}>
      <Collapsible id={`settings-${id}`} title={title} meta={meta}>
        <div className={s.sectionBody}>{children}</div>
      </Collapsible>
    </div>
  )
}
