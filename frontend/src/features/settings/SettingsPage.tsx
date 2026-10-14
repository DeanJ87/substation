// Settings (design v2 A4, spec 008): tabs down the side (owner 2026-10-11: tabbed, not one long scroll), and a save
// bar that collects grading, stacking and calibration changes until they are saved. Links to a section
// (/settings#workers) open its tab.
import { useNavigate, useRouterState } from '@tanstack/react-router'
import { useEffect, type ReactNode } from 'react'
import { Appearance } from './Appearance'
import { Bin } from './Bin'
import { DraftProvider, useSettings } from './draft'
import { IgnoreRules } from './IgnoreRules'
import { PathPatterns } from './PathPatterns'
import { Rigs } from './Rigs'
import { Updates } from './Updates'
import {
  CalibrationMatching,
  Folders,
  FilePaths,
  Grading,
  MetadataSources,
  Notifications,
  PlateSolving,
  Stacking,
  PostProcessing,
  Users,
  Workers,
} from './Sections'
import s from './settings.module.css'

type Tab = { id: string; label: string; sections: string[]; body: ReactNode }

const TABS: Tab[] = [
  {
    id: 'library',
    label: 'Library',
    sections: ['folders', 'paths', 'sources', 'patterns', 'ignored', 'bin'],
    body: (
      <>
        <Folders />
        <FilePaths />
        <MetadataSources />
        <PathPatterns />
        <IgnoreRules />
        <Bin />
      </>
    ),
  },
  { id: 'rigs', label: 'Rigs', sections: ['rigs'], body: <Rigs /> },
  {
    id: 'processing',
    label: 'Processing',
    sections: ['grading', 'calibration', 'stacking', 'post', 'solving'],
    body: (
      <>
        <Grading />
        <CalibrationMatching />
        <Stacking />
        <PostProcessing />
        <PlateSolving />
      </>
    ),
  },
  {
    id: 'workers',
    label: 'Workers',
    sections: ['workers', 'updates'],
    body: (
      <>
        <Workers />
        <Updates />
      </>
    ),
  },
  { id: 'notifications', label: 'Notifications', sections: ['notifications'], body: <Notifications /> },
  { id: 'users', label: 'Users', sections: ['users'], body: <Users /> },
  { id: 'appearance', label: 'Appearance', sections: ['appearance'], body: <Appearance /> },
]

export function SettingsPage() {
  const settings = useSettings()
  const readOnly = !settings.data?.can_edit
  const hash = useRouterState({ select: (st) => st.location.hash })
  const navigate = useNavigate()
  const tab = TABS.find((t) => t.id === hash || t.sections.includes(hash)) ?? TABS[0]
  // a link to one section of a tab scrolls to it
  useEffect(() => {
    if (hash && hash !== tab.id) document.getElementById(hash)?.scrollIntoView({ block: 'start' })
  }, [hash, tab.id])
  return (
    <DraftProvider readOnly={readOnly}>
      <div className={s.layout}>
        <div className={s.rail} role="tablist" aria-label="Settings" aria-orientation="vertical">
          {TABS.map((t) => (
            <button
              key={t.id}
              type="button"
              role="tab"
              aria-selected={t === tab}
              className={s.railTab}
              onClick={() => void navigate({ to: '/settings', hash: t.id, replace: true })}
            >
              {t.label}
            </button>
          ))}
        </div>
        <div className={s.page} role="tabpanel" aria-label={tab.label}>
          {tab.sections.length > 1 && <h1>{tab.label}</h1>}
          {readOnly && <p className="muted">Admins only.</p>}
          {tab.body}
        </div>
      </div>
    </DraftProvider>
  )
}
