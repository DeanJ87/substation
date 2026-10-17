// Where a file is, as this viewer's machine sees it (owner 2026-10-12). Server paths are mapped by prefix: the site's mappings (Settings → File paths), with
// this browser's own overrides first, so a Windows PC sees Z:\Photography\… and a Mac /Volumes/Photography/….
import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { api, unwrap } from '../api/client'
import { toast } from './Toasts'
import v from '../features/v2/v2.module.css'

export type PathMap = { from: string; to: string }
const KEY = 'sst-path-map'
const MODE_KEY = 'sst-file-mode'
export type FileMode = 'open' | 'download'

/** How this browser gets at a file (2026-10-15): open it where it is on a mapped share, or download it. Per
 * browser, since a machine without the share mounted can only download. */
export function fileMode(): FileMode {
  try {
    return localStorage.getItem(MODE_KEY) === 'download' ? 'download' : 'open'
  } catch {
    return 'open'
  }
}

export function saveFileMode(mode: FileMode) {
  try {
    localStorage.setItem(MODE_KEY, mode)
  } catch {
    /* private window: opening in place stays the default */
  }
}

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

/** The folder holding a file as an smb:// link, from a mapping to a network share (\\host\share\…), so a Mac can open
 * it in Finder with one click (2026-10-17). A browser may not open a file on the machine itself; Finder can. */
export function shareFolderUrl(path: string, maps: PathMap[]): string | null {
  const unc = maps.filter((m) => /^\\\\[^\\]+\\/.test(m.to))
  const mapped = mapPath(path, unc)
  if (mapped === path) return null
  const parts = mapped.replace(/^\\\\/, '').split('\\').filter(Boolean)
  if (parts.length < 3) return null // host, share and the file at least
  return 'smb://' + parts.slice(0, -1).map(encodeURIComponent).join('/') + '/'
}

const isMac = () => typeof navigator !== 'undefined' && /Mac/i.test(navigator.userAgent)

export function useSitePathMap(): PathMap[] {
  const q = useQuery({ queryKey: ['settings'], queryFn: async () => unwrap(await api.GET('/settings')) })
  const p = (q.data?.processing as { paths?: { map?: PathMap[] } } | undefined)?.paths?.map
  return Array.isArray(p) ? p : []
}

export function FilePath({
  path,
  download,
  className,
}: {
  path: string
  download?: string | null // the same file over the web, for a browser set to download
  className?: string
}) {
  const site = useSitePathMap()
  const [shown] = useState(() => localPathMap())
  const [mode] = useState(fileMode)
  if (!path) return null
  const maps = [...shown, ...site.filter((s) => !shown.some((l) => l.from === s.from))]
  const local = mapPath(path, maps)
  const name = path.split('/').pop() ?? 'file'
  const finder = isMac() ? shareFolderUrl(path, [...site, ...shown]) : null
  if (download && (mode === 'download' || local === path)) {
    // set to download, or no mapping reaches this folder from here: a path the machine can't open is no use
    return (
      <span
        className={className}
        style={{ display: 'inline-flex', gap: 6, alignItems: 'center', minWidth: 0 }}
      >
        <a className={v.pill} href={download} download>
          Download
        </a>
        <code style={{ overflowWrap: 'anywhere', fontSize: 12 }} title={path}>
          {name}
        </code>
      </span>
    )
  }
  return (
    <span
      className={className}
      style={{ display: 'inline-flex', flexWrap: 'wrap', gap: 6, alignItems: 'center', minWidth: 0 }}
    >
      {/* in a narrow column the path takes its own line and the buttons wrap below it */}
      <code style={{ overflowWrap: 'anywhere', fontSize: 12, flex: '1 1 16em' }} title={path}>
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
      {finder && (
        <a className={v.pill} href={finder} title="Open the folder holding this file in Finder">
          Open in Finder
        </a>
      )}
    </span>
  )
}
