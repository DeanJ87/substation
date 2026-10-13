// Where a file is, as this viewer's machine sees it (owner 2026-10-12). Server paths are mapped by prefix: the site's mappings (Settings → File paths), with
// this browser's own overrides first, so a Windows PC sees Z:\Photography\… and a Mac /Volumes/Photography/….
import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { api, unwrap } from '../api/client'
import { toast } from './Toasts'
import v from '../features/v2/v2.module.css'

export type PathMap = { from: string; to: string }
const KEY = 'sst-path-map'

export function localPathMap(): PathMap[] {
  try {
    const saved = JSON.parse(localStorage.getItem(KEY) || '[]')
    return Array.isArray(saved) ? saved : []
  } catch {
    return []
  }
}

export function saveLocalPathMap(map: PathMap[]) {
  try {
    localStorage.setItem(KEY, JSON.stringify(map.filter((m) => m.from && m.to)))
  } catch {
    /* private window: the site's mappings still apply */
  }
}

/** The path with the longest matching prefix swapped; Windows targets get backslashes. */
export function mapPath(path: string, maps: PathMap[]): string {
  const hit = maps
    .filter((m) => m.from && (path === m.from || path.startsWith(m.from.replace(/\/$/, '') + '/')))
    .sort((a, b) => b.from.length - a.from.length)[0]
  if (!hit) return path
  const rest = path.slice(hit.from.replace(/\/$/, '').length)
  const windows = /^[A-Za-z]:|^\\\\/.test(hit.to)
  const joined = hit.to.replace(/[\\/]$/, '') + (windows ? rest.replace(/\//g, '\\') : rest)
  return joined
}

export function useSitePathMap(): PathMap[] {
  const q = useQuery({ queryKey: ['settings'], queryFn: async () => unwrap(await api.GET('/settings')) })
  const p = (q.data?.processing as { paths?: { map?: PathMap[] } } | undefined)?.paths?.map
  return Array.isArray(p) ? p : []
}

export function FilePath({ path, className }: { path: string; className?: string }) {
  const site = useSitePathMap()
  const [shown] = useState(() => localPathMap())
  if (!path) return null
  const local = mapPath(path, [...shown, ...site.filter((s) => !shown.some((l) => l.from === s.from))])
  return (
    <span className={className} style={{ display: 'inline-flex', gap: 6, alignItems: 'center', minWidth: 0 }}>
      <code style={{ overflowWrap: 'anywhere', fontSize: 12 }} title={path}>
        {local}
      </code>
      <button
        type="button"
        className={v.pill}
        onClick={() =>
          navigator.clipboard?.writeText(local).then(
            () => toast('Path copied'),
            () => toast("Couldn't copy the path"),
          )
        }
      >
        Copy path
      </button>
    </span>
  )
}
