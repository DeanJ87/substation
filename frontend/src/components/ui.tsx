// The primitive layer (007-DR-38): every screen builds from these, on the v2 look. Buttons, chips, segmented
// controls, stat tiles, tables, filter and grade meters, form fields, page headers, and empty, error and loading
// states. Colour rules live in design/substation-tokens.css; formatting in features/format.ts.
import {
  forwardRef,
  useEffect,
  useId,
  useState,
  type ButtonHTMLAttributes,
  type InputHTMLAttributes,
  type ReactNode,
  type SelectHTMLAttributes,
} from 'react'
import { filterColour, filterName } from './filters'
import { Help } from './Help'
import s from './ui.module.css'

const cx = (...c: (string | false | null | undefined)[]) => c.filter(Boolean).join(' ')

/* ------------------------------------------------------------------------------------------------ buttons */

export type ButtonVariant = 'default' | 'primary' | 'danger' | 'ghost' | 'link'
export type ButtonSize = 'md' | 'sm'

/** The class for something that looks like a button but isn't one (a router Link, a label). */
export function buttonClass({
  variant = 'default',
  size = 'md',
  iconOnly = false,
}: { variant?: ButtonVariant; size?: ButtonSize; iconOnly?: boolean } = {}) {
  return cx(s.button, s[variant], size === 'sm' && s.sm, iconOnly && s.iconOnly)
}

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: ButtonVariant
  size?: ButtonSize
  /** A leading icon (an inline svg or a glyph). */
  icon?: ReactNode
  /** Only the icon shows; `aria-label` is required then. */
  iconOnly?: boolean
  /** A toggle button: sets aria-pressed. */
  pressed?: boolean
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { variant = 'default', size = 'md', icon, iconOnly, pressed, className, children, ...rest },
  ref,
) {
  return (
    <button
      ref={ref}
      type="button"
      aria-pressed={pressed}
      className={cx(buttonClass({ variant, size, iconOnly }), className)}
      {...rest}
    >
      {icon && (
        <span className={s.icon} aria-hidden="true">
          {icon}
        </span>
      )}
      {!iconOnly && children}
    </button>
  )
})

/** A destructive action asks in the page, not in a browser dialog (007-DR-16): the button turns into the
 * question with the confirming action and Cancel. Escape cancels. */
export function ConfirmButton({
  children,
  question,
  confirm,
  onConfirm,
  className,
  size = 'md',
  variant = 'default',
}: {
  children: ReactNode
  question: ReactNode
  confirm: string
  onConfirm: () => void
  className?: string
  size?: ButtonSize
  variant?: ButtonVariant
}) {
  const [asking, setAsking] = useState(false)
  useEffect(() => {
    if (!asking) return
    const esc = (e: KeyboardEvent) => e.key === 'Escape' && setAsking(false)
    document.addEventListener('keydown', esc)
    return () => document.removeEventListener('keydown', esc)
  }, [asking])
  if (!asking)
    return (
      <button
        type="button"
        className={className ?? buttonClass({ variant, size })}
        onClick={(e) => {
          e.stopPropagation() // inside a clickable row, asking mustn't also open the row
          setAsking(true)
        }}
      >
        {children}
      </button>
    )
  return (
    <span className={s.confirm} role="group" aria-label="Confirm">
      <span>{question}</span>
      <Button
        variant="danger"
        size="sm"
        onClick={(e) => {
          e.stopPropagation()
          setAsking(false)
          onConfirm()
        }}
      >
        {confirm}
      </Button>
      <Button
        size="sm"
        onClick={(e) => {
          e.stopPropagation()
          setAsking(false)
        }}
      >
        Cancel
      </Button>
    </span>
  )
}

/* ------------------------------------------------------------------------------------------------ chips */

export type Tone = 'neutral' | 'ok' | 'warn' | 'bad' | 'info'

/** One chip family. Static (a tag), a toggle (`pressed` + `onClick`), or removable (`onRemove`). A `count`
 * sits at the end in tabular figures. */
export function Chip({
  children,
  tone = 'neutral',
  pressed,
  onClick,
  onRemove,
  removeLabel,
  count,
  title,
  icon,
  className,
}: {
  children: ReactNode
  tone?: Tone
  pressed?: boolean
  onClick?: () => void
  onRemove?: () => void
  removeLabel?: string
  count?: number | string
  title?: string
  icon?: ReactNode
  className?: string
}) {
  const body = (
    <>
      {icon && (
        <span className={s.icon} aria-hidden="true">
          {icon}
        </span>
      )}
      <span>{children}</span>
      {count != null && <span className={s.chipCount}>{count}</span>}
    </>
  )
  const cls = cx(s.chip, tone !== 'neutral' && s[`tone_${tone}`], className)
  if (onClick)
    return (
      <button
        type="button"
        className={cx(cls, s.chipButton)}
        aria-pressed={pressed}
        title={title}
        onClick={onClick}
      >
        {body}
      </button>
    )
  return (
    <span className={cls} title={title}>
      {body}
      {onRemove && (
        <button
          type="button"
          className={s.chipRemove}
          aria-label={removeLabel ?? `Remove ${typeof children === 'string' ? children : ''}`.trim()}
          onClick={onRemove}
        >
          ×
        </button>
      )}
    </span>
  )
}

/** A static tag: a Chip with no actions. */
export const Tag = (props: { children: ReactNode; tone?: Tone; title?: string; icon?: ReactNode }) => (
  <Chip {...props} />
)

export function ChipGroup({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className={s.chipGroup} role="group" aria-label={label}>
      {children}
    </div>
  )
}

/** A filter's name in its colour: a swatch and the canonical name ("Halpha" → Hα). Never CSS-uppercased. */
export function FilterTag({ filter, plain }: { filter: string | null | undefined; plain?: boolean }) {
  const name = filterName(filter) || '—'
  return (
    <span className={cx(s.filterTag, plain && s.filterPlain)}>
      <span className={s.swatch} style={{ background: filterColour(filter) }} aria-hidden="true" />
      {name}
    </span>
  )
}

/* ------------------------------------------------------------------------------------------------ segmented */

export type SegmentOption<T extends string> = {
  value: T
  label: ReactNode
  count?: number
  title?: string
  disabled?: boolean
}

/** Joined buttons for one choice among a few (a view mode, a sort). Arrow keys move the choice. */
export function SegmentedControl<T extends string>({
  label,
  value,
  options,
  onChange,
  size = 'md',
}: {
  label: string
  value: T
  options: SegmentOption<T>[]
  onChange: (v: T) => void
  size?: ButtonSize
}) {
  const move = (dir: number) => {
    const live = options.filter((o) => !o.disabled)
    const i = live.findIndex((o) => o.value === value)
    const next = live[(i + dir + live.length) % live.length]
    if (next) onChange(next.value)
  }
  return (
    <div
      className={cx(s.segment, size === 'sm' && s.segmentSm)}
      role="radiogroup"
      aria-label={label}
      tabIndex={-1}
      onKeyDown={(e) => {
        if (e.key === 'ArrowRight' || e.key === 'ArrowDown') {
          e.preventDefault()
          move(1)
        } else if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') {
          e.preventDefault()
          move(-1)
        }
      }}
    >
      {options.map((o) => (
        <button
          key={o.value}
          type="button"
          role="radio"
          aria-checked={o.value === value}
          tabIndex={o.value === value ? 0 : -1}
          disabled={o.disabled}
          title={o.title}
          onClick={() => onChange(o.value)}
        >
          {o.label}
          {o.count != null && <span className={s.chipCount}>{o.count}</span>}
        </button>
      ))}
    </div>
  )
}

/* ------------------------------------------------------------------------------------------------ stats */

/** A labelled figure: "Integration 12h 50m". Figures are plain text in tabular sans, never the accent. */
export function StatTile({
  label,
  value,
  unit,
  detail,
  help,
  tone,
  children,
}: {
  label: ReactNode
  value: ReactNode
  unit?: ReactNode
  detail?: ReactNode
  help?: ReactNode
  tone?: 'ok' | 'warn' | 'bad'
  /** Extra content under the figure (a meter). */
  children?: ReactNode
}) {
  return (
    <section className={s.stat}>
      <div className={s.statLabel}>
        <span>{label}</span>
        {help && <Help topic={typeof label === 'string' ? label : 'this figure'}>{help}</Help>}
      </div>
      <div className={cx(s.statValue, tone && s[`tone_${tone}`])}>
        {value}
        {unit && <span className={s.statUnit}>{unit}</span>}
      </div>
      {children}
      {detail && <div className={s.statDetail}>{detail}</div>}
    </section>
  )
}

export function StatGrid({ children, label }: { children: ReactNode; label?: string }) {
  return (
    <div className={s.statGrid} role={label ? 'group' : undefined} aria-label={label}>
      {children}
    </div>
  )
}

/* ------------------------------------------------------------------------------------------------ meters */

/** A plain progress bar (a job, a move, a goal): neutral data fill, or a status tone. */
export function Meter({
  value,
  max = 1,
  label,
  tone,
}: {
  value: number
  max?: number
  label: string
  tone?: 'ok' | 'warn' | 'bad'
}) {
  const pct = max > 0 ? Math.max(0, Math.min(100, (value / max) * 100)) : 0
  return (
    <div
      className={s.meter}
      role="progressbar"
      aria-label={label}
      aria-valuemin={0}
      aria-valuemax={max}
      aria-valuenow={value}
    >
      <span className={tone ? s[`fill_${tone}`] : undefined} style={{ width: `${pct}%` }} />
    </div>
  )
}

/** One filter's integration: kept in the filter's colour, waiting striped, rejected hatched grey, a goal tick.
 * Seconds in, and `max` sets the scale shared by a list of them. */
export function FilterMeter({
  filter,
  kept,
  waiting = 0,
  rejected = 0,
  goal,
  max,
  value,
}: {
  filter: string
  kept: number
  waiting?: number
  rejected?: number
  goal?: number | null
  max?: number
  /** The figure at the end of the row, already formatted. */
  value?: ReactNode
}) {
  const scale = Math.max(max ?? 0, kept + waiting + rejected, goal ?? 0, 1)
  const w = (n: number) => `${(Math.max(0, n) / scale) * 100}%`
  const parts = [
    rejected > 0 ? `${Math.round((rejected / (kept + waiting + rejected)) * 100)}% rejected` : '',
    waiting > 0 ? 'some waiting to be graded' : '',
  ].filter(Boolean)
  return (
    <div className={s.filterMeter}>
      <FilterTag filter={filter} plain />
      <div
        className={s.fmTrack}
        role="img"
        aria-label={`${filterName(filter)}: ${typeof value === 'string' ? value : ''}${parts.length ? `, ${parts.join(', ')}` : ''}`}
      >
        <span className={s.fmKept} style={{ width: w(kept), background: filterColour(filter) }} />
        {waiting > 0 && <span className={s.fmWait} style={{ width: w(waiting) }} />}
        {rejected > 0 && <span className={s.fmRej} style={{ width: w(rejected) }} />}
        {goal ? <span className={s.fmGoal} style={{ left: w(goal) }} /> : null}
      </div>
      {value != null && <span className={s.fmValue}>{value}</span>}
    </div>
  )
}

/** Grades of a set of subs: kept (sage, solid), down-weighted (slate, hatched), rejected (grey, cross-hatched),
 * waiting (outline). Status colours, never filter colours; the legend says which is which. */
export function GradeMeter({
  kept,
  down = 0,
  rejected = 0,
  pending = 0,
  legend = false,
}: {
  kept: number
  down?: number
  rejected?: number
  pending?: number
  legend?: boolean
}) {
  const total = kept + down + rejected + pending
  const w = (n: number) => `${total ? (n / total) * 100 : 0}%`
  const items = [
    { n: kept, label: 'kept', cls: s.gKept },
    { n: down, label: 'down-weighted', cls: s.gDown },
    { n: rejected, label: 'rejected', cls: s.gRej },
    { n: pending, label: 'not graded', cls: s.gPend },
  ].filter((x) => x.n > 0)
  const text = items.map((x) => `${x.n} ${x.label}`).join(', ') || 'no subs'
  return (
    <div className={s.grade}>
      <div className={s.gTrack} role="img" aria-label={`Grades: ${text}`} title={text}>
        {items.map((x) => (
          <span key={x.label} className={x.cls} style={{ width: w(x.n) }} />
        ))}
      </div>
      {legend && (
        <div className={s.gLegend} aria-hidden="true">
          {items.map((x) => (
            <span key={x.label}>
              <i className={x.cls} />
              {x.n} {x.label}
            </span>
          ))}
        </div>
      )}
    </div>
  )
}

/* ------------------------------------------------------------------------------------------------ tables */

/** The one table style. `cards` turns rows into cards on a phone (007-DR-29); `compact` tightens the rows. */
export function Table({
  label,
  children,
  compact,
  cards,
  className,
}: {
  label: string
  children: ReactNode
  compact?: boolean
  cards?: boolean
  className?: string
}) {
  return (
    <div className={s.tableWrap}>
      <table className={cx(s.table, compact && s.compact, cards && 'cards', className)} aria-label={label}>
        {children}
      </table>
    </div>
  )
}

export const tableClass = s.table

/* ------------------------------------------------------------------------------------------------ forms */

/** A labelled control: the label above, an optional hint or error under it. */
export function Field({
  label,
  hint,
  error,
  help,
  children,
  inline,
  className,
}: {
  label: ReactNode
  hint?: ReactNode
  error?: ReactNode
  help?: ReactNode
  children: ReactNode
  inline?: boolean
  className?: string
}) {
  return (
    <label className={cx(s.field, inline && s.fieldInline, className)}>
      <span className={s.fieldLabel}>
        {label}
        {help && <Help topic={typeof label === 'string' ? label : 'this field'}>{help}</Help>}
      </span>
      {children}
      {error ? (
        <span className={s.fieldError} role="alert">
          {error}
        </span>
      ) : (
        hint && <span className={s.fieldHint}>{hint}</span>
      )}
    </label>
  )
}

export const Input = forwardRef<
  HTMLInputElement,
  InputHTMLAttributes<HTMLInputElement> & { size_?: ButtonSize }
>(function Input({ className, size_, ...rest }, ref) {
  return <input ref={ref} className={cx(s.control, size_ === 'sm' && s.controlSm, className)} {...rest} />
})

export function Select({
  className,
  options,
  size_,
  children,
  ...rest
}: SelectHTMLAttributes<HTMLSelectElement> & {
  options?: { value: string | number; label: string; disabled?: boolean }[]
  size_?: ButtonSize
}) {
  return (
    <select className={cx(s.control, s.select, size_ === 'sm' && s.controlSm, className)} {...rest}>
      {children}
      {options?.map((o) => (
        <option key={o.value} value={o.value} disabled={o.disabled}>
          {o.label}
        </option>
      ))}
    </select>
  )
}

export function Checkbox({ label, ...rest }: InputHTMLAttributes<HTMLInputElement> & { label: ReactNode }) {
  return (
    <label className={s.check}>
      <input type="checkbox" {...rest} />
      <span>{label}</span>
    </label>
  )
}

/** Fields that belong together, with a quiet heading instead of the browser's fieldset border. */
export function FieldGroup({ legend, children }: { legend: ReactNode; children: ReactNode }) {
  return (
    <fieldset className={s.group}>
      <legend className={s.groupLegend}>{legend}</legend>
      {children}
    </fieldset>
  )
}

/* ------------------------------------------------------------------------------------------------ layout */

export function Card({
  children,
  pad = true,
  className,
}: {
  children: ReactNode
  pad?: boolean
  className?: string
}) {
  return <section className={cx(s.card, pad && s.cardPad, className)}>{children}</section>
}

/** A page's head: breadcrumbs, the title, one short line under it, and the page's actions. */
export function PageHeader({
  crumbs,
  title,
  sub,
  actions,
  help,
}: {
  crumbs?: ReactNode
  title: ReactNode
  sub?: ReactNode
  actions?: ReactNode
  help?: ReactNode
}) {
  return (
    <header className={s.pageHead}>
      <div className={s.pageTitle}>
        {crumbs && (
          <nav className={s.crumbs} aria-label="Breadcrumbs">
            {crumbs}
          </nav>
        )}
        <h1>
          {title}
          {help && <Help topic={typeof title === 'string' ? title : 'this page'}>{help}</Help>}
        </h1>
        {sub && <div className={s.pageSub}>{sub}</div>}
      </div>
      {actions && <div className={s.pageActions}>{actions}</div>}
    </header>
  )
}

/** A section heading inside a page, with an optional ? and actions on the right. */
export function SectionHead({
  title,
  help,
  actions,
  as: H = 'h2',
}: {
  title: ReactNode
  help?: ReactNode
  actions?: ReactNode
  as?: 'h2' | 'h3'
}) {
  const id = useId()
  return (
    <div className={s.sectionHead}>
      <H id={id}>
        {title}
        {help && <Help topic={typeof title === 'string' ? title : 'this section'}>{help}</Help>}
      </H>
      {actions && <div className={s.pageActions}>{actions}</div>}
    </div>
  )
}

/* ------------------------------------------------------------------------------------------------ states */

export function EmptyState({
  title,
  children,
  action,
  inline,
}: {
  title?: ReactNode
  children?: ReactNode
  action?: ReactNode
  inline?: boolean
}) {
  if (inline)
    return (
      <p className={s.emptyInline}>
        {title}
        {title && children ? ' ' : ''}
        {children}
      </p>
    )
  return (
    <section className={s.state}>
      {title && <h3>{title}</h3>}
      {children && <div className={s.stateBody}>{children}</div>}
      {action && <div className={s.stateAction}>{action}</div>}
    </section>
  )
}

/** An error in a sentence, with the raw detail (a log, a traceback) folded away beneath it. */
export function ErrorState(props: {
  title: string
  children?: ReactNode
  detail?: string | null
  onRetry?: () => void
  inline?: boolean
}) {
  return (
    <section className={cx(s.state, s.error, props.inline && s.errorInline)} role="alert">
      <h3>{props.title}</h3>
      {props.children && <div className={s.stateBody}>{props.children}</div>}
      {props.detail && <ErrorDetail detail={props.detail} />}
      {props.onRetry && (
        <div className={s.stateAction}>
          <Button onClick={props.onRetry}>Retry</Button>
        </div>
      )}
    </section>
  )
}

/** A raw error (Siril's output, a traceback) behind a "Details" disclosure. */
export function ErrorDetail({ detail, summary = 'Details' }: { detail: string; summary?: string }) {
  return (
    <details className={s.detail}>
      <summary>{summary}</summary>
      <pre>{detail}</pre>
    </details>
  )
}

/** A long error reduced to its first sentence or line, for a one-line message. */
export function firstLine(text: string | null | undefined, max = 120): string {
  if (!text) return ''
  const line =
    text
      .split('\n')
      .map((l) => l.trim())
      .find(Boolean) ?? ''
  return line.length > max ? `${line.slice(0, max - 1).trimEnd()}…` : line
}

/** A raw error (a worker's or Siril's) as one short sentence: Siril's "Trial #n:" bookkeeping dropped, cut before
 * the first per-trial detail, the first line only. The full text belongs behind ErrorDetail. */
export function shortError(text: string | null | undefined, max = 120): string {
  if (!text) return ''
  const plain = text.replace(/^\s*(Trial #\d+:\s*)+/i, '').trim()
  const i = plain.search(/:\s*Trial #\d+/i)
  return firstLine(i > 0 ? `${plain.slice(0, i)}.` : plain, max)
}

/** A small spinner for anything waiting on the server (owner 2026-10-11: loading must be obvious). */
export function Spinner({ label = 'Loading' }: { label?: string }) {
  return <span className={s.spinner} role="status" aria-label={label} />
}

/** A grey placeholder the size of what's coming, so the page doesn't jump when it arrives. */
export function Skeleton({
  width = '100%',
  height = 16,
}: {
  width?: number | string
  height?: number | string
}) {
  return <span className={s.skeleton} style={{ width, height }} aria-hidden="true" />
}

/** A page waiting for its first answer: a title bar and two blocks where the content will be. */
export function PageLoading() {
  return (
    <div className={s.pageLoading} aria-busy="true" aria-label="Loading">
      <Skeleton width={240} height={30} />
      <Skeleton height={120} />
      <Skeleton height={260} />
    </div>
  )
}
