// Dependent fields (018-DR-17): a child control's choices come from its parent's actual data, a child that no
// longer fits is cleared when the parent changes, and no choice leads to an empty result.

/** The value if it is still one of the choices, else nothing. */
export function keepIfOffered<T>(value: T | undefined | null, offered: readonly T[]): T | undefined {
  return value != null && offered.includes(value) ? value : undefined
}

/** The chosen values that are still offered, in the order chosen. */
export function keepOffered<T>(chosen: readonly T[], offered: readonly T[]): T[] {
  return chosen.filter((x) => offered.includes(x))
}

export type Range = { from?: string; to?: string }

/** Set one end of a date range (ISO days) so that from ≤ to always holds: moving one end past the other moves
 * the other end with it, so a range can never be empty. */
export function setRangeEnd(range: Range, end: 'from' | 'to', value: string | undefined): Range {
  const next = { ...range, [end]: value || undefined }
  if (next.from && next.to && next.from > next.to) {
    if (end === 'from') next.to = next.from
    else next.from = next.to
  }
  return next
}

/** Whether an ISO day sits inside a range (open ends allowed). */
export function inRange(day: string, range: Range): boolean {
  return (!range.from || day >= range.from) && (!range.to || day <= range.to)
}

/** Today as an ISO day in local time, for a date field's `min` when the past makes no sense (an expiry). */
export function todayIso(now: Date = new Date()): string {
  const p = (n: number) => String(n).padStart(2, '0')
  return `${now.getFullYear()}-${p(now.getMonth() + 1)}-${p(now.getDate())}`
}
