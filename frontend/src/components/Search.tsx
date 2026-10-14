// Search from the header (007-DR-26): collections, datasets, nights and files. "/" focuses it from anywhere.
import { useQuery } from '@tanstack/react-query'
import { useNavigate } from '@tanstack/react-router'
import { useEffect, useMemo, useRef, useState } from 'react'
import { api, unwrap } from '../api/client'
import s from './Search.module.css'

type Hit = { key: string; group: string; title: string; detail: string; go: () => void }

function useDebounced<T>(value: T, ms: number): T {
  const [v, setV] = useState(value)
  useEffect(() => {
    const t = setTimeout(() => setV(value), ms)
    return () => clearTimeout(t)
  }, [value, ms])
  return v
}

function plural(n: number, word: string): string {
  return `${n.toLocaleString('en-GB')} ${word}${n === 1 ? '' : 's'}`
}

export function Search() {
  const navigate = useNavigate()
  const input = useRef<HTMLInputElement>(null)
  const box = useRef<HTMLDivElement>(null)
  const [q, setQ] = useState('')
  const [open, setOpen] = useState(false)
  const [at, setAt] = useState(0)
  const term = useDebounced(q.trim(), 200)
  const found = useQuery({
    queryKey: ['search', term],
    queryFn: async () => unwrap(await api.GET('/search', { params: { query: { q: term } } })),
    enabled: term.length >= 2,
    staleTime: 30_000,
  })

  useEffect(() => {
    const key = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement
      if (e.key !== '/' || e.metaKey || e.ctrlKey || t.closest('input, textarea, select, [contenteditable]'))
        return
      e.preventDefault()
      input.current?.focus()
      setOpen(true)
    }
    const away = (e: MouseEvent) => {
      if (!box.current?.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('keydown', key)
    document.addEventListener('mousedown', away)
    return () => {
      document.removeEventListener('keydown', key)
      document.removeEventListener('mousedown', away)
    }
  }, [])

  const hits = useMemo<Hit[]>(() => {
    const r = found.data
    if (!r || term.length < 2) return []
    const done = (to: () => void) => () => {
      to()
      setOpen(false)
      setQ('')
      input.current?.blur()
    }
    return [
      ...r.collections.map((c) => ({
        key: `c${c.id}`,
        group: 'Collections',
        title: c.name,
        detail: plural(c.datasets, 'dataset'),
        go: done(() => void navigate({ to: '/collections/$id', params: { id: String(c.id) } })),
      })),
      ...r.datasets.map((d) => ({
        key: `d${d.id}`,
        group: 'Datasets',
        title: d.name,
        detail: plural(d.subs, 'sub'),
        go: done(() => void navigate({ to: '/datasets/$id', params: { id: String(d.id) } })),
      })),
      ...r.nights.map((n) => ({
        key: `n${n.date}`,
        group: 'Nights',
        title: new Date(`${n.date}T12:00:00`).toLocaleDateString('en-GB', {
          weekday: 'short',
          day: 'numeric',
          month: 'long',
          year: 'numeric',
        }),
        detail: plural(n.datasets, 'dataset'),
        go: done(() => void navigate({ to: '/nights/$date', params: { date: n.date } })),
      })),
      ...r.files.map((f) => ({
        key: `f${f.sha256}`,
        group: 'Files',
        title: f.name,
        detail: f.folder,
        go: done(() => void navigate({ to: '/subs/$sha', params: { sha: f.sha256 } })),
      })),
    ]
  }, [found.data, term, navigate])

  function onKey(e: React.KeyboardEvent) {
    if (e.key === 'Escape') {
      setOpen(false)
      input.current?.blur()
    } else if (e.key === 'ArrowDown') {
      e.preventDefault()
      setAt((a) => Math.min(a + 1, hits.length - 1))
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      setAt((a) => Math.max(a - 1, 0))
    } else if (e.key === 'Enter' && hits[at]) {
      e.preventDefault()
      hits[at].go()
    }
  }

  const showing = open && term.length >= 2
  return (
    <div className={s.search} ref={box}>
      <input
        ref={input}
        type="search"
        className={s.input}
        placeholder="Search"
        aria-label="Search collections, datasets, nights and files"
        aria-expanded={showing}
        aria-controls="search-results"
        role="combobox"
        value={q}
        onChange={(e) => {
          setQ(e.target.value)
          setAt(0)
          setOpen(true)
        }}
        onFocus={() => setOpen(true)}
        onKeyDown={onKey}
      />
      {!q && (
        <kbd className={s.hint} aria-hidden="true">
          /
        </kbd>
      )}
      {showing && (
        <div className={s.results} id="search-results" role="listbox">
          {found.isFetching && !hits.length && <p className={s.note}>Searching…</p>}
          {!found.isFetching && !hits.length && <p className={s.note}>Nothing matches “{term}”.</p>}
          {hits.map((h, i) => (
            <div key={h.key}>
              {(i === 0 || hits[i - 1].group !== h.group) && <p className={s.group}>{h.group}</p>}
              <button
                type="button"
                role="option"
                aria-selected={i === at}
                className={`${s.hit} ${i === at ? s.hitAt : ''}`}
                onMouseEnter={() => setAt(i)}
                onClick={h.go}
              >
                <span className={s.title}>{h.title}</span>
                <span className={s.detail}>{h.detail}</span>
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
