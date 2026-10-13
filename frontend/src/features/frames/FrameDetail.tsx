// Frame detail drawer: every value with its source (constitution II), copies, history and raw headers.
import * as Dialog from '@radix-ui/react-dialog'
import { useState } from 'react'
import { Button } from '../../components/ui'
import { Collapsible } from '../../components/Collapsible'
import { VerdictBadge } from '../../components/VerdictBadge'
import { useFrame } from '../datasets/queries'
import { nightText, timeText } from '../format'
import { FrameValues } from './FrameValues'
import { IgnoreActions } from './IgnoreActions'
import s from './frames.module.css'

type HistoryEvent = { kind: string; details: Record<string, unknown> }

function describe({ kind, details }: HistoryEvent): string {
  const d = (k: string) => String(details[k] ?? '')
  switch (kind) {
    case 'discovered':
      return `Found at ${d('path')}`
    case 'copied':
      return `Another copy found at ${d('path')}`
    case 'moved':
      return `Moved from ${d('from')} to ${d('to')}`
    case 'renamed':
      return `Renamed from ${d('from')} to ${d('to')}`
    case 'missing':
      return `${d('path')} is no longer on disk`
    case 'reappeared':
      return `${d('path')} is back on disk`
    case 'replaced':
      return `${d('path')} was overwritten with different content`
    default:
      return `${kind} ${JSON.stringify(details)}`
  }
}

export function FrameDetail({ sha256, onClose }: { sha256: string | null; onClose: () => void }) {
  const q = useFrame(sha256)
  const f = q.data
  const [headerImage, setHeaderImage] = useState(0)

  return (
    <Dialog.Root open={sha256 !== null} onOpenChange={(o) => !o && onClose()}>
      <Dialog.Portal>
        <Dialog.Overlay className={s.overlay} />
        <Dialog.Content className={s.drawer} aria-describedby={undefined}>
          <div className={s.top}>
            <Dialog.Title className={s.title}>
              {f ? f.primary_path.split('/').pop() : 'Loading…'}
            </Dialog.Title>
            <Dialog.Close asChild>
              <Button>Close</Button>
            </Dialog.Close>
          </div>
          {q.isError && <p role="alert">{q.error.message}</p>}
          {f && (
            <>
              <dl className={s.facts}>
                <dt className="label">Type</dt>
                <dd>
                  {f.frame_type.replace('_', ' ')} <span className="muted">· {f.classification_reason}</span>
                </dd>
                <dt className="label">Night</dt>
                <dd>{f.night ? nightText(f.night) : 'unknown'}</dd>
                <dt className="label">Time</dt>
                <dd className="mono">
                  {f.date_obs_utc ? `${timeText(f.date_obs_utc)} (${f.date_obs_utc} UTC)` : '—'}
                </dd>
                <dt className="label">Content</dt>
                <dd className="mono" title={f.sha256}>
                  sha256 {f.sha256.slice(0, 16)}… · {(f.size_bytes / 1e6).toFixed(1)} MB · {f.format}
                  {f.image_count > 1 && ` · ${f.image_count} images`}
                </dd>
                {f.error && (
                  <>
                    <dt className="label">Error</dt>
                    <dd role="alert">{f.error}</dd>
                  </>
                )}
              </dl>

              {f.verdicts.length > 0 && (
                <Collapsible id="frame-decisions" title="Decisions" meta={f.verdicts.length}>
                  <ul className={s.plain}>
                    {f.verdicts.map((v, i) => (
                      <li key={i}>
                        <VerdictBadge
                          state={v.verdict === 'reject' ? 'reject' : v.verdict === 'keep' ? 'down' : 'accept'}
                        />{' '}
                        <span className="muted">
                          {v.source === 'nina_bad_prefix' ? 'Rejected in NINA (BAD_ prefix)' : `by ${v.by}`} ·{' '}
                          {new Date(v.at).toLocaleString('en-GB')}
                        </span>
                      </li>
                    ))}
                  </ul>
                </Collapsible>
              )}

              <FrameValues frame={f} />

              <IgnoreActions frame={f} />

              <Collapsible id="frame-copies" title="Copies on disk" meta={f.copy_list.length}>
                <ul className={s.plain}>
                  {f.copy_list.map((c) => (
                    <li key={`${c.library}/${c.path}`} className="mono">
                      {c.library}/{c.path} {!c.present && <span className="muted">(missing)</span>}
                      {c.is_bad_prefixed && <span className="muted"> (NINA thumbs-down copy)</span>}
                    </li>
                  ))}
                </ul>
              </Collapsible>

              {f.history.length > 0 && (
                <Collapsible id="frame-history" title="History" meta={f.history.length}>
                  <ul className={`${s.plain} ${s.pane}`}>
                    {f.history.map((h, i) => (
                      <li key={i}>
                        <span className="mono muted">{new Date(h.at).toLocaleString('en-GB')}</span>{' '}
                        {describe(h as HistoryEvent)}
                      </li>
                    ))}
                  </ul>
                </Collapsible>
              )}

              <Collapsible id="frame-headers" title="Headers">
                {f.headers.length > 1 && (
                  <div className={s.imageTabs} role="tablist">
                    {f.headers.map((h) => (
                      <button
                        key={h.image_index}
                        role="tab"
                        aria-selected={headerImage === h.image_index}
                        onClick={() => setHeaderImage(h.image_index)}
                      >
                        {h.image_id || `image ${h.image_index}`}
                      </button>
                    ))}
                  </div>
                )}
                {f.headers
                  .filter((h) => h.image_index === headerImage)
                  .map((h) => (
                    <pre key={h.image_index} className={`${s.headers} mono`}>
                      {Object.entries(h.keywords as Record<string, { value: unknown; comment: string }>)
                        .map(([k, v]) => `${k.padEnd(8)}= ${String(v.value).padEnd(28)} / ${v.comment}`)
                        .join('\n')}
                    </pre>
                  ))}
              </Collapsible>
            </>
          )}
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  )
}
