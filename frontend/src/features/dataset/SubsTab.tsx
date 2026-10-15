// Subs (design v2 D1): tiles grouped by session, newest first; filters; click selects, shift-click selects a
// range, Ctrl/Cmd-A selects the session; the bulk bar and A, W, R apply to the selection; U reverts.
import { getRouteApi, Link, useNavigate } from '@tanstack/react-router'
import { useEffect, useMemo, useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { api, unwrap } from '../../api/client'
import { Button, ConfirmButton } from '../../components/ui'
import { Modal } from '../../components/Modal'
import { SubView } from '../sub/SubDetail'
import { binMessage, useBinFiles } from '../settings/Bin'
import { offerUndo, useAgree } from '../changes/changes'
import { Collapsible } from '../../components/Collapsible'
import { LoadMore } from '../../components/LoadMore'
import { useProgressive } from '../../components/useProgressive'
import { VerdictIcon, type VerdictState } from '../../components/VerdictBadge'
import { integrationText, nightText } from '../format'
import {
  fwhmText,
  num,
  previewUrl,
  useStartStack,
  useVerdict,
  type DatasetT,
  type Session,
  type Sub,
} from '../v2/hooks'
import v from '../v2/v2.module.css'
import { conditionsText } from './DatasetScreen'
import s from './dataset.module.css'

type Filter = 'all' | 'flagged' | 'accept' | 'down' | 'reject' | 'manual' | 'waiting'

const route = getRouteApi('/app/datasets/$id')

/** What Review used to list (003-DR-05, spec 012): rejected, down-weighted or near a threshold, not decided by hand. */
export function isFlagged(x: Sub): boolean {
  return !x.manual && (x.verdict === 'reject' || x.verdict === 'down' || x.near_threshold)
}

export function verdictState(sub: Sub): VerdictState {
  if (sub.verdict === 'accept') return 'accept'
  if (sub.verdict === 'down') return 'down'
  if (sub.verdict === 'reject') return 'reject'
  if (sub.awaiting_reason) return 'await'
  return 'integ'
}

/** A sub's capture time, local, to the minute: what tells the subs of one night apart. */
function tileTime(iso: string): string {
  return new Date(iso).toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' })
}

export function shortName(file: string): string {
  const m = file.match(/(_\d{3,5})(\.[a-z]+)?$/i)
  return m ? `…${m[1]}` : file.replace(/\.(xisf|fits?|fz)$/i, '')
}

export function SubsTab({
  dataset,
  subs,
  sessions,
}: {
  dataset: DatasetT
  subs: Sub[]
  sessions: Session[]
}) {
  const search = route.useSearch()
  const [localFilter, setLocalFilter] = useState<Filter>('all')
  const filter: Filter = search.show === 'flagged' ? 'flagged' : localFilter
  const setFilter = (f: Filter) => {
    setLocalFilter(f === 'flagged' ? 'all' : f)
    void navigate({
      to: '/datasets/$id',
      params: { id: String(dataset.id) },
      search: { ...search, show: f === 'flagged' ? 'flagged' : undefined },
      replace: true,
    })
  }
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [anchor, setAnchor] = useState<string | null>(null)
  const verdict = useVerdict()
  const navigate = useNavigate()
  const stack = useStartStack(dataset.id)
  const qc = useQueryClient()
  const bin = useBinFiles()
  const agree = useAgree(dataset.id)
  const selectAll = (list: Sub[]) => setSelected(new Set(list.map((x) => x.sha256)))
  const binRejected = useMutation({
    mutationFn: async () =>
      unwrap(await api.POST('/datasets/{id}/bin-rejected', { params: { path: { id: dataset.id } } })),
    onSuccess: (r) => offerUndo(qc, binMessage(r), r.change_id),
    onSettled: () => void qc.invalidateQueries(),
    meta: { failed: "Couldn't bin the rejected subs" },
  })
  // 004 T009: a master of exactly these subs, whatever their grades (included and excluded by hand)
  // the Masters tab opens at once, with the new master waiting there
  const stackSelected = () => {
    stack.mutate({
      rule: 'default',
      include: [...selected],
      exclude: subs.map((x) => x.sha256).filter((x) => !selected.has(x)),
    })
    void navigate({
      to: '/datasets/$id',
      params: { id: String(dataset.id) },
      search: { tab: 'masters' },
    })
  }
  // the viewer (spec 012): a modal over this grid, stepping through what the grid shows
  const openSub = (sha: string) =>
    void navigate({
      to: '/datasets/$id',
      params: { id: String(dataset.id) },
      search: { ...search, tab: 'subs', sub: sha },
    })
  const closeSub = () =>
    void navigate({
      to: '/datasets/$id',
      params: { id: String(dataset.id) },
      search: { ...search, sub: undefined },
    })
  const openReview = () => {
    const first = [...selected][0]
    if (first) openSub(first)
  }

  const visible = useMemo(
    () =>
      subs.filter((x) =>
        filter === 'all'
          ? true
          : filter === 'flagged'
            ? isFlagged(x)
            : filter === 'manual'
              ? x.manual
              : filter === 'waiting'
                ? !x.verdict
                : x.verdict === filter,
      ),
    [subs, filter],
  )
  const byNight = useMemo(() => {
    const m = new Map<string, Sub[]>()
    for (const x of visible) {
      const k = x.night ?? 'unknown'
      m.set(k, [...(m.get(k) ?? []), x])
    }
    return [...m.entries()].sort((a, b) => b[0].localeCompare(a[0]))
  }, [visible])
  const groups = useProgressive(byNight, 8, filter)
  const order = useMemo(() => byNight.flatMap(([, list]) => list.map((x) => x.sha256)), [byNight])
  const count = (f: Filter) =>
    f === 'flagged'
      ? subs.filter(isFlagged).length
      : f === 'manual'
        ? subs.filter((x) => x.manual).length
        : f === 'waiting'
          ? subs.filter((x) => !x.verdict).length
          : subs.filter((x) => x.verdict === f).length

  function click(sha: string, e: React.MouseEvent) {
    const next = new Set(selected)
    if (e.shiftKey && anchor) {
      const [a, b] = [order.indexOf(anchor), order.indexOf(sha)].sort((p, q) => p - q)
      for (const k of order.slice(a, b + 1)) next.add(k)
    } else if (next.has(sha)) next.delete(sha)
    else next.add(sha)
    setSelected(next)
    setAnchor(sha)
  }

  function apply(kind: 'accept' | 'keep' | 'reject' | 'auto') {
    if (!selected.size) return
    verdict.mutate({ sha256s: [...selected], verdict: kind })
    setSelected(new Set())
  }

  useEffect(() => {
    function key(e: KeyboardEvent) {
      if (search.sub || (e.target as HTMLElement).closest('input, select, textarea')) return
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'a') {
        const night = anchor ? subs.find((x) => x.sha256 === anchor)?.night : byNight[0]?.[0]
        const list = byNight.find(([n]) => n === night)?.[1] ?? []
        if (list.length) {
          e.preventDefault()
          setSelected(new Set(list.map((x) => x.sha256)))
        }
        return
      }
      if (e.metaKey || e.ctrlKey || e.altKey || !selected.size) return
      const k = e.key.toLowerCase()
      if (k === 'a') apply('accept')
      else if (k === 'w') apply('keep')
      else if (k === 'r') apply('reject')
      else if (k === 'u') apply('auto')
      else if (k === 'escape') setSelected(new Set())
      else if (k === 'enter' && selected.size === 1) openReview()
    }
    window.addEventListener('keydown', key)
    return () => window.removeEventListener('keydown', key)
  })

  const selNights = [...new Set(subs.filter((x) => selected.has(x.sha256)).map((x) => x.night))]
  const sessionInfo = (n: string) => sessions.find((x) => x.night === n)

  return (
    <div className={s.subs}>
      <div className={s.filterBar}>
        <div className={v.pills}>
          <button className={v.pill} aria-pressed={filter === 'all'} onClick={() => setFilter('all')}>
            Sessions <strong>All {dataset.nights}</strong>
          </button>
          {count('flagged') > 0 && (
            <button
              className={v.pill}
              aria-pressed={filter === 'flagged'}
              onClick={() => setFilter('flagged')}
              title="Rejected, down-weighted or within 10% of a threshold, and not decided by hand"
            >
              Flagged <span className={v.mono}>{count('flagged')}</span>
            </button>
          )}
          {(
            [
              ['accept', 'Accepted', 'accept'],
              ['down', 'Down-weighted', 'down'],
              ['reject', 'Rejected', 'reject'],
            ] as const
          ).map(([f, label, st]) => (
            <button key={f} className={v.pill} aria-pressed={filter === f} onClick={() => setFilter(f)}>
              <VerdictIcon state={st} size={13} title="" /> {label} <span className={v.mono}>{count(f)}</span>
            </button>
          ))}
          <button className={v.pill} aria-pressed={filter === 'manual'} onClick={() => setFilter('manual')}>
            M Manual <span className={v.mono}>{count('manual')}</span>
          </button>
          {count('waiting') > 0 && (
            <button
              className={v.pill}
              aria-pressed={filter === 'waiting'}
              onClick={() => setFilter('waiting')}
            >
              <VerdictIcon state="await" size={13} title="" /> Not graded yet{' '}
              <span className={v.mono}>{count('waiting')}</span>
            </button>
          )}
        </div>
        <span className={v.actions}>
          {count('flagged') > 0 && (
            <ConfirmButton
              question={
                <>
                  Agree with the automatic grades of all {count('flagged')} flagged subs? Each becomes your
                  own verdict and leaves the review list. You can undo it.
                </>
              }
              confirm="Agree"
              onConfirm={() => agree.mutate({})}
            >
              Agree with {count('flagged')} flagged
            </ConfirmButton>
          )}
          {count('reject') > 0 && (
            <ConfirmButton
              question={
                <>Bin all {count('reject')} rejected subs? You can restore them from Settings → Bin.</>
              }
              confirm="Bin them"
              onConfirm={() => binRejected.mutate()}
            >
              Bin {count('reject')} rejected
            </ConfirmButton>
          )}
          <span className={v.muted}>Sort: capture time</span>
        </span>
      </div>

      {selected.size > 0 && (
        <div className={s.bulkBar} role="toolbar" aria-label="Selected subs">
          <span>
            <strong>{selected.size} selected</strong>{' '}
            <span className={v.muted}>
              {selNights.length === 1
                ? `from ${nightText(selNights[0])}`
                : `from ${selNights.length} sessions`}
            </span>
          </span>
          <div className={v.actions}>
            <Button onClick={() => apply('accept')}>
              <VerdictIcon state="accept" size={14} title="" /> Accept <kbd>A</kbd>
            </Button>
            <Button onClick={() => apply('keep')}>
              <VerdictIcon state="down" size={14} title="" /> Down-weight <kbd>W</kbd>
            </Button>
            <ConfirmButton
              question={
                <>
                  Bin {selected.size} sub{selected.size === 1 ? '' : 's'}?
                </>
              }
              confirm="Bin"
              onConfirm={() => {
                bin.mutate([...selected])
                setSelected(new Set())
              }}
            >
              Bin
            </ConfirmButton>
            <Button onClick={() => apply('reject')}>
              <VerdictIcon state="reject" size={14} title="" /> Reject <kbd>R</kbd>
            </Button>
            <Button onClick={() => apply('auto')}>
              Clear override <kbd>U</kbd>
            </Button>
            {selected.size === 1 && (
              <Button onClick={openReview}>
                Open <kbd>Enter</kbd>
              </Button>
            )}
            <Button
              onClick={stackSelected}
              disabled={selected.size < 2}
              title="Stack these subs regardless of grade"
            >
              Stack these {selected.size}
            </Button>
            {selected.size < visible.length && (
              <Button onClick={() => selectAll(visible)}>Select all {visible.length} shown</Button>
            )}
            <Button onClick={() => setSelected(new Set())}>
              Deselect <kbd>Esc</kbd>
            </Button>
          </div>
        </div>
      )}

      {byNight.length === 0 && <p className={v.empty}>No subs match this filter.</p>}
      {/* sessions a few at a time, and each session's tiles a slice at a time in its own scrolling pane
          (owner 2026-10-11: enormous lists load as they scroll, inside their section) */}
      {groups.visible.map(([night, list]) => (
        <SessionGroup
          key={night}
          datasetId={dataset.id}
          night={night}
          list={list}
          info={sessionInfo(night)}
          resetKey={filter}
          selected={selected}
          onClick={click}
          onOpen={openSub}
          onSelectAll={() => selectAll(list)}
          onAgree={() => agree.mutate({ night })}
        />
      ))}
      <LoadMore hasMore={groups.hasMore} loading={false} onMore={groups.more} />
      {search.sub && (
        <Modal label="Sub" onClose={closeSub}>
          <SubView
            sha={search.sub}
            list={{
              shas: order.includes(search.sub) ? order : subs.map((x) => x.sha256),
              label: {
                all: 'All subs',
                flagged: 'Flagged subs',
                accept: 'Accepted subs',
                down: 'Down-weighted subs',
                reject: 'Rejected subs',
                manual: 'Decided by hand',
                waiting: 'Not graded yet',
              }[filter],
              onPick: (sha) =>
                void navigate({
                  to: '/datasets/$id',
                  params: { id: String(dataset.id) },
                  search: { ...search, sub: sha },
                  replace: true,
                }),
            }}
            afterVerdict={
              filter === 'flagged'
                ? () => {
                    // reviewing: the next flagged sub, as Review did
                    const i = order.indexOf(search.sub!)
                    const next = order[i + 1]
                    if (next)
                      void navigate({
                        to: '/datasets/$id',
                        params: { id: String(dataset.id) },
                        search: { ...search, sub: next },
                        replace: true,
                      })
                  }
                : undefined
            }
          />
        </Modal>
      )}
    </div>
  )
}

function SessionGroup({
  datasetId,
  night,
  list,
  info,
  resetKey,
  selected,
  onClick,
  onOpen,
  onSelectAll,
  onAgree,
}: {
  datasetId: number
  night: string
  list: Sub[]
  info: Session | undefined
  resetKey: unknown
  selected: Set<string>
  onClick: (sha: string, e: React.MouseEvent) => void
  onOpen: (sha: string) => void
  onSelectAll: () => void
  onAgree: () => void
}) {
  const { visible, hasMore, more } = useProgressive(list, 120, resetKey)
  const flagged = list.filter(isFlagged).length
  const allSelected = list.every((x) => selected.has(x.sha256))
  return (
    <Collapsible
      id={`dataset-${datasetId}-session-${night}`}
      title={nightText(night)}
      meta={`${list.length.toLocaleString('en-GB')} subs · ${integrationText(list.reduce((n, x) => n + (x.exptime_s ?? 0), 0))}`}
      className={s.session}
    >
      <div className={s.sessionHead}>
        {info ? (
          <span
            className={v.muted}
            title={
              Object.entries(info.condition_sources ?? {})
                .map(([k, src]) => `${k}: ${src}`)
                .join('\n') || 'No conditions recorded'
            }
          >
            {conditionsText(info.conditions) || 'no conditions recorded'}
            {Object.keys(info.condition_sources ?? {}).length > 0 &&
              ` · from ${[...new Set(Object.values(info.condition_sources ?? {}))].join(', ')}`}
          </span>
        ) : (
          <span />
        )}
        <span className={v.actions}>
          {!allSelected && (
            <button type="button" className={v.pill} onClick={onSelectAll}>
              Select all {list.length.toLocaleString('en-GB')}
            </button>
          )}
          {flagged > 0 && (
            <button
              type="button"
              className={v.pill}
              onClick={onAgree}
              title="Each flagged sub of this night keeps its automatic grade as your own verdict, and leaves the review list"
            >
              Agree with {flagged} flagged
            </button>
          )}
          <Link to="/nights/$date" params={{ date: night }}>
            The night
          </Link>
        </span>
      </div>
      <div className={s.tilePane}>
        <div className={s.tiles}>
          {visible.map((x) => (
            <Tile
              key={x.sha256}
              sub={x}
              selected={selected.has(x.sha256)}
              onClick={(e) => onClick(x.sha256, e)}
              onOpen={() => onOpen(x.sha256)}
            />
          ))}
        </div>
        <LoadMore hasMore={hasMore} loading={false} onMore={more} />
      </div>
    </Collapsible>
  )
}

function Tile({
  sub,
  selected,
  onClick,
  onOpen,
}: {
  sub: Sub
  selected: boolean
  onClick: (e: React.MouseEvent) => void
  onOpen: () => void
}) {
  const st = verdictState(sub)
  const title = sub.reason ?? sub.awaiting_reason ?? sub.error ?? 'Not graded yet'
  return (
    <div className={`${s.tile} ${selected ? s.tileSelected : ''}`} title={title}>
      <button
        className={s.tileHit}
        onClick={onClick}
        onDoubleClick={onOpen}
        aria-pressed={selected}
        aria-label={`Select ${sub.file}: ${title}`}
      />
      <div className={s.thumb}>
        {sub.has_preview && <img src={previewUrl(sub.sha256)} alt="" loading="lazy" />}
      </div>
      <div className={s.tileTop}>
        <span className={s.disc}>
          <VerdictIcon state={st} size={14} title="" />
        </span>
        {sub.manual && <span className={s.manual}>M</span>}
        {sub.source === 'nina' && <span className={s.manual}>NINA</span>}
        {sub.provisional && <span className={s.manual}>?</span>}
        <span className={`${s.check} ${selected ? s.checkOn : ''}`} aria-hidden />
      </div>
      <div className={s.tileFoot}>
        {/* what tells subs apart at a glance (2026-10-15): when it was taken and how it measured; the file name, which
            is mostly the same for every sub, on hover */}
        <button
          type="button"
          onClick={onOpen}
          className={`${s.tileName} ${s.tileOpen} ${v.mono}`}
          title={sub.file}
          aria-label={`Open ${sub.file}`}
        >
          {sub.time ? tileTime(sub.time) : shortName(sub.file)}
          {sub.exptime_s ? <span className={v.muted}> · {sub.exptime_s} s</span> : null}
        </button>
        <div className={`${v.mono} ${s.tileStats}`}>
          {fwhmText(sub)} · ★ {num(sub.stars)}
          {sub.guiding != null ? ` · ${sub.guiding.toFixed(2)}″ RMS` : ''}
        </div>
      </div>
    </div>
  )
}
