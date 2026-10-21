import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Link, Outlet, useNavigate } from '@tanstack/react-router'
import { useEffect, useRef, useState } from 'react'
import { signOut, type SessionUser } from '../api/auth'
import { api, unwrap } from '../api/client'
import { BusyBar } from '../components/Busy'
import { Toasts } from '../components/Toasts'
import { KeyHelp } from '../components/KeyHelp'
import { Search } from '../components/Search'
import { Lockup } from '../components/Logo'
import { ThemeProvider } from '../design/ThemeContext'
import { UndoKeys } from '../features/changes/changes'
import { useQueueSummary } from '../features/queue/queries'
import s from './frame.module.css'

const NAV = [
  { to: '/', label: 'Library' },
  { to: '/finished', label: 'Finished' },
  { to: '/calibration', label: 'Calibration' },
  { to: '/map', label: 'Map' },
  { to: '/activity', label: 'Activity' },
  { to: '/bin', label: 'Bin' },
  { to: '/settings', label: 'Settings' },
] as const

export function AppFrame({ user }: { user: SessionUser }) {
  return (
    <ThemeProvider>
      <Frame user={user} />
    </ThemeProvider>
  )
}

/** Design v2 header (007-DR-05): mark and wordmark, the five sections with counts, the watched folders and an
 * account menu. Activity's count turns to failures while any are unresolved, so a failure is never silent. */
function Frame({ user }: { user: SessionUser }) {
  const qc = useQueryClient()
  const navigate = useNavigate()
  const health = useQuery({
    queryKey: ['health'],
    queryFn: async () => unwrap(await api.GET('/health')),
    refetchInterval: 30_000,
  })
  const libraries =
    (health.data as { libraries?: { name: string; status: string }[] } | undefined)?.libraries ?? []
  const act = useQueueSummary()
  const running = act.data?.running ?? 0
  const failed = act.data?.failed_open ?? 0
  const healthy = libraries.length > 0 && libraries.every((l) => l.status === 'ok' || l.status === 'watching')

  async function out() {
    await signOut()
    qc.clear()
    await navigate({ to: '/sign-in' })
  }

  return (
    <div className={s.app}>
      <BusyBar />
      <Toasts />
      <UndoKeys />
      <header className={s.header}>
        <Link to="/" className={s.brand} aria-label="SubStation home">
          <Lockup size={22} />
        </Link>
        <nav aria-label="Main" className={s.nav}>
          {NAV.map((n) => (
            <Link
              key={n.to}
              to={n.to}
              className={s.navLink}
              activeProps={{ className: `${s.navLink} ${s.navActive}` }}
            >
              {n.label}
              {n.to === '/activity' && failed > 0 ? (
                <span
                  className={`${s.count} ${s.countBad}`}
                  aria-label={`${failed} failed jobs`}
                  title={`${failed} failed`}
                >
                  {failed} failed
                </span>
              ) : (
                n.to === '/activity' &&
                running > 0 && (
                  <span className={s.count} aria-label={`${running} jobs running`}>
                    {running}
                  </span>
                )
              )}
            </Link>
          ))}
        </nav>
        <div className={s.headerRight}>
          <Search />
          <Link
            to="/settings"
            className={s.watching}
            title={libraries.map((l) => `/data/library/${l.name}: ${l.status}`).join('\n')}
          >
            <span className={`${s.dot} ${healthy ? s.dotOk : s.dotWarn}`} aria-hidden="true" />
            {libraries.length
              ? `Watching ${libraries.length} folder${libraries.length === 1 ? '' : 's'}`
              : 'No folders mounted'}
          </Link>
          <span className={s.divider} aria-hidden="true" />
          <AccountMenu
            name={user.username}
            version={(health.data as { version?: string } | undefined)?.version ?? ''}
            onSignOut={() => void out()}
          />
        </div>
      </header>
      <main className={s.main}>
        <Outlet />
      </main>
      <KeyHelp />
    </div>
  )
}

function AccountMenu({ name, version, onSignOut }: { name: string; version: string; onSignOut: () => void }) {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (!open) return
    const close = (e: MouseEvent | KeyboardEvent) => {
      if (e instanceof KeyboardEvent ? e.key === 'Escape' : !ref.current?.contains(e.target as Node))
        setOpen(false)
    }
    document.addEventListener('mousedown', close)
    document.addEventListener('keydown', close)
    return () => {
      document.removeEventListener('mousedown', close)
      document.removeEventListener('keydown', close)
    }
  }, [open])
  return (
    <div className={s.account} ref={ref}>
      <button
        type="button"
        className={s.accountBtn}
        aria-haspopup="menu"
        aria-expanded={open}
        onClick={() => setOpen(!open)}
      >
        <span className={s.avatar} aria-hidden="true">
          {name.slice(0, 1).toUpperCase()}
        </span>
        {name}
      </button>
      {open && (
        <div className={s.menu} role="menu">
          <Link
            to="/settings"
            hash="appearance"
            role="menuitem"
            className={s.menuItem}
            onClick={() => setOpen(false)}
          >
            Appearance
          </Link>
          <button type="button" role="menuitem" className={s.menuItem} onClick={onSignOut}>
            Sign out
          </button>
          <div className={s.version} title={`SubStation ${version || 'dev'}`}>
            {versionShort(version)}
          </div>
        </div>
      )}
    </div>
  )
}

/** "0.1.0.dev0 · poc-substation · 9c18d24 · 15 Oct 2026 18:19" → two short lines: the version and commit, then when
 * it was built. The whole string is the tooltip. */
function versionShort(v: string) {
  const [ver, , commit, built] = (v || 'dev').split(' · ')
  return (
    <>
      <span>
        SubStation {ver}
        {commit ? ` · ${commit}` : ''}
      </span>
      {built && <span>Built {built}</span>}
    </>
  )
}
