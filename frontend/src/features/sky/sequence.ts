// The nights of a target played end to end (owner 2026-10-15): one clock from the first sub of the first night to the
// last sub of the last, skipping the days in between, so Play shows each night in turn.

export type Span = { first: string; last: string }
export type Seq = { nights: { start: number; end: number; offset: number }[]; total: number }

export function sequence(nights: Span[]): Seq {
  let offset = 0
  const out = nights.map((n) => {
    const start = Date.parse(n.first)
    const end = Math.max(start, Date.parse(n.last))
    const seg = { start, end, offset }
    offset += end - start
    return seg
  })
  return { nights: out, total: offset }
}

/** Where a point on the joined clock falls: which night, and the real time then. */
export function locate(seq: Seq, pos: number): { night: number; t: number } {
  const p = Math.min(Math.max(pos, 0), seq.total)
  for (let i = 0; i < seq.nights.length; i++) {
    const n = seq.nights[i]
    if (p <= n.offset + (n.end - n.start) || i === seq.nights.length - 1)
      return { night: i, t: n.start + Math.min(p - n.offset, n.end - n.start) }
  }
  return { night: 0, t: seq.nights[0]?.start ?? 0 }
}

/** The joined clock's position at a real time in night `i`. */
export function position(seq: Seq, i: number, t: number): number {
  const n = seq.nights[i]
  return n ? n.offset + Math.min(Math.max(t - n.start, 0), n.end - n.start) : 0
}
