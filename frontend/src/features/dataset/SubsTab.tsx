// Subs (design v2 D1): tiles grouped by session, newest first; filters; click selects, shift-click selects a
// range, Ctrl/Cmd-A selects the session; the bulk bar and A, W, R apply to the selection; U reverts.
import { getRouteApi, Link, useNavigate } from '@tanstack/react-router'
import { useEffect, useMemo, useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { api, unwrap } from '../../api/client'
import { Button, Chip, ChipGroup, ConfirmButton } from '../../components/ui'
import { Modal } from '../../components/Modal'
import { SubView } from '../sub/SubDetail'
import { binMessage, useBinFiles } from '../settings/Bin'
import { offerUndo, useAgree } from '../changes/changes'
import { Collapsible } from '../../components/Collapsible'
import { LoadMore } from '../../components/LoadMore'
import { useProgressive } from '../../components/useProgressive'
import { VerdictIcon, type VerdictState } from '../../components/VerdictBadge'
import {
  clockText,
  countText,
  exposureText,
  integrationText,
  nightShort,
  nightText,
  numText,
} from '../format'
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
const tileTime = clockText

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

  const mixedExposure = new Set(subs.map((x) => x.exptime_s)).size > 1
  const selNights = [...new Set(subs.filter((x) => selected.has(x.sha256)).map((x) => x.night))]
  const sessionInfo = (n: string) => sessions.find((x) => x.night === n)

  return (
    <div className={s.subs}>
      <div className={s.filterBar}>
        <ChipGroup label="Show">
          <Chip pressed={filter === 'all'} onClick={() => setFilter('all')} count={countText(subs.length)}>
            All
          </Chip>
          {count('flagged') > 0 && (
            <Chip
              pressed={filter === 'flagged'}
              onClick={() => setFilter('flagged')}
              count={count('flagged')}
              title={flaggedTitle(subs)}
            >
              Needs a look
            </Chip>
          )}
          {(
            [
              ['accept', 'Accepted', 'accept'],
              ['down', 'Down-weighted', 'down'],
              ['reject', 'Rejected', 'reject'],
            ] as const
          ).map(([f, label, st]) => (
            <Chip
              key={f}
              pressed={filter === f}
              onClick={() => setFilter(f)}
              count={count(f)}
              icon={<VerdictIcon state={st} size={13} title="" />}
            >
              {label}
            </Chip>
          ))}
          {count('manual') > 0 && (
            <Chip pressed={filter === 'manual'} onClick={() => setFilter('manual')} count={count('manual')}>
              Decided by hand
            </Chip>
          )}
          {count('waiting') > 0 && (
            <Chip
              pressed={filter === 'waiting'}
              onClick={() => setFilter('waiting')}
              count={count('waiting')}
              icon={<VerdictIcon state="await" size={13} title="" />}
            >
              Not graded yet
            </Chip>
          )}
        </ChipGroup>
        {/* one action bar, for what's shown (C15): agree while reviewing, bin while looking at the rejects */}
        <span className={v.actions}>
          {filter === 'flagged' && count('flagged') > 0 && (
            <ConfirmButton
              question={<>Keep the automatic grade of all {count('flagged')} as your own? You can undo it.</>}
              confirm="Agree"
              onConfirm={() => agree.mutate({})}
            >
              Agree with all {count('flagged')}
            </ConfirmButton>
          )}
          {filter === 'reject' && count('reject') > 0 && (
            <ConfirmButton
              variant="danger"
              question={<>Bin all {count('reject')} rejected subs? You can restore them from the Bin.</>}
              confirm="Bin them"
              onConfirm={() => binRejected.mutate()}
            >
              Bin all {count('reject')}
            </ConfirmButton>
          )}
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
            <Button size="sm" onClick={() => apply('accept')}>
              <VerdictIcon state="accept" size={14} title="" /> Accept <kbd>A</kbd>
            </Button>
            <Button size="sm" onClick={() => apply('keep')}>
              <VerdictIcon state="down" size={14} title="" /> Down-weight <kbd>W</kbd>
            </Button>
            <Button size="sm" onClick={() => apply('reject')}>
              <VerdictIcon state="reject" size={14} title="" /> Reject <kbd>R</kbd>
            </Button>
            <Button
              size="sm"
              variant="ghost"
              onClick={() => apply('auto')}
              title="Back to the automatic grade (U)"
            >
              Clear override
            </Button>
            {selected.size === 1 && (
              <Button size="sm" variant="ghost" onClick={openReview}>
                Open
              </Button>
            )}
            <Button
              size="sm"
              variant="ghost"
              onClick={stackSelected}
              disabled={selected.size < 2}
              title={
                selected.size < 2 ? 'Choose at least two subs' : 'Stack these subs whatever their grades'
              }
            >
              Stack these
            </Button>
            {selected.size < visible.length && (
              <Button size="sm" variant="ghost" onClick={() => selectAll(visible)}>
                Select all {countText(visible.length)}
              </Button>
            )}
            <ConfirmButton
              size="sm"
              variant="danger"
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
            <Button
              size="sm"
              variant="ghost"
              onClick={() => setSelected(new Set())}
              aria-label="Deselect (Esc)"
            >
              ×
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
          onAgree={filter === 'flagged' ? () => agree.mutate({ night }) : undefined}
          mixedExposure={mixedExposure}
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
              onClose: closeSub,
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
  mixedExposure,
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
  onAgree?: () => void
  mixedExposure: boolean
}) {
  const { visible, hasMore, more } = useProgressive(list, 120, resetKey)
  const flagged = list.filter(isFlagged).length
  const allSelected = list.every((x) => selected.has(x.sha256))
  return (
    <Collapsible
      id={`dataset-${datasetId}-session-${night}`}
      title={nightText(night)}
      meta={
        <>
          <span>
            {countText(list.length)} subs ·{' '}
            {integrationText(list.reduce((n, x) => n + (x.exptime_s ?? 0), 0))}
          </span>
          {!allSelected && (
            <Button size="sm" variant="ghost" onClick={onSelectAll}>
              Select all
            </Button>
          )}
          {onAgree && flagged > 0 && (
            <Button
              size="sm"
              variant="ghost"
              onClick={onAgree}
              title="Keep the automatic grades of this night's flagged subs as your own"
            >
              Agree with {flagged}
            </Button>
          )}
          {night !== 'unknown' && (
            <Link to="/nights/$date" params={{ date: night }} className="quiet">
              Night of {nightShort(night)} →
            </Link>
          )}
        </>
      }
      className={s.session}
    >
      {/* conditions only when there are some (C14); where each came from on hover */}
      {info && conditionsText(info.conditions) && (
        <div
          className={`${v.muted} ${s.sessionHead}`}
          title={Object.entries(info.condition_sources ?? {})
            .map(([k, src]) => `${k}: ${src}`)
            .join('\n')}
        >
          {conditionsText(info.conditions)}
        </div>
      )}
      <div className={s.tilePane}>
        <div className={s.tiles}>
          {visible.map((x) => (
            <Tile
              key={x.sha256}
              sub={x}
              selected={selected.has(x.sha256)}
              onClick={(e) => onClick(x.sha256, e)}
              onOpen={() => onOpen(x.sha256)}
              showExposure={mixedExposure}
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
  showExposure,
}: {
  sub: Sub
  selected: boolean
  onClick: (e: React.MouseEvent) => void
  onOpen: () => void
  showExposure: boolean
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
          className={`${s.tileName} ${s.tileOpen}`}
          title={sub.file}
          aria-label={`Open ${sub.file}`}
        >
          {sub.time ? tileTime(sub.time) : shortName(sub.file)}
          {showExposure && sub.exptime_s ? (
            <span className={v.muted}> · {exposureText(sub.exptime_s)}</span>
          ) : null}
        </button>
        <div className={`${v.mono} ${s.tileStats}`}>
          {fwhmText(sub)} · ★ {num(sub.stars)}
          {sub.guiding != null ? ` · ${numText(sub.guiding, 2)}″ RMS` : ''}
        </div>
      </div>
    </div>
  )
}

/** Why "Needs a look" counts what it does: "6 rejected, 1 down-weighted, 1 near a threshold" (C16). */
function flaggedTitle(subs: Sub[]): string {
  const f = subs.filter(isFlagged)
  const rej = f.filter((x) => x.verdict === 'reject').length
  const down = f.filter((x) => x.verdict === 'down').length
  const near = f.length - rej - down
  return [
    rej ? `${rej} rejected` : '',
    down ? `${down} down-weighted` : '',
    near ? `${near} accepted but near a threshold` : '',
  ]
    .filter(Boolean)
    .join(', ')
}
