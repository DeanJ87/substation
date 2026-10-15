// A fake SubStation API for page tests (005-DR-29): every response is made up from the OpenAPI contract, so a page
// renders with data of the right shape and no real library's names, paths or places ever enter the repo.
import { vi } from 'vitest'
import spec from '../api/openapi.json'

type Schema = {
  $ref?: string
  type?: string | string[]
  format?: string
  enum?: unknown[]
  const?: unknown
  items?: Schema
  properties?: Record<string, Schema>
  required?: string[]
  additionalProperties?: boolean | Schema
  anyOf?: Schema[]
  oneOf?: Schema[]
  allOf?: Schema[]
  default?: unknown
}
type Op = { responses?: Record<string, { content?: Record<string, { schema?: Schema }> }> }

const doc = spec as unknown as {
  paths: Record<string, Record<string, Op>>
  components: { schemas: Record<string, Schema> }
}

export const SHA = 'ab'.repeat(32)

function resolve(s: Schema): Schema {
  return s.$ref ? doc.components.schemas[s.$ref.split('/').pop()!] : s
}

/** One plausible value for a field, from its schema and its name. */
export function fake(schema: Schema | undefined, name = '', depth = 0): unknown {
  if (!schema) return null
  const s = resolve(schema)
  if (s.const !== undefined) return s.const
  if (s.enum) return s.enum[0]
  const alts = s.anyOf ?? s.oneOf
  if (alts) {
    const real = alts.find((a) => resolve(a).type !== 'null')
    return real ? fake(real, name, depth) : null
  }
  if (s.allOf) return fake(s.allOf[0], name, depth)
  const type = Array.isArray(s.type) ? s.type.find((t) => t !== 'null') : s.type
  const n = name.toLowerCase()
  switch (type) {
    case 'object': {
      if (depth > 6) return {}
      const out: Record<string, unknown> = {}
      for (const [k, v] of Object.entries(s.properties ?? {})) out[k] = fake(v, k, depth + 1)
      return out
    }
    case 'array':
      return depth > 6 ? [] : [0, 1].map((i) => withIndex(fake(s.items, name, depth + 1), i))
    case 'integer':
      return n.includes('count') || n.endsWith('s') ? 3 : 1
    case 'number':
      if (n === 'lat' || n.endsWith('_lat')) return 51.5
      if (n === 'lon' || n.endsWith('_lon')) return -0.1
      return n.includes('pct') || n.includes('fraction') ? 0.5 : 2.5
    case 'boolean':
      return false
    case 'string':
      if (s.format === 'date-time' || n.endsWith('_at') || n === 'time' || n.endsWith('_utc'))
        return '2026-10-01T21:30:00Z'
      if (s.format === 'date' || n === 'night' || n === 'date' || n.endsWith('_night')) return '2026-10-01'
      if (n.includes('sha') || n === 'frame_id' || n === 'hash') return SHA
      if (n.includes('path') || n === 'folder') return '/data/library/Target/Light/sub_0001.fit'
      if (n.includes('url') || n === 'download' || n === 'preview' || n === 'href') return '/media/x.jpg'
      if (n === 'time' || n.endsWith('_time')) return '03:30'
      return `${name || 'text'} value`
    default:
      return null
  }
}

/** Second items of a list get their own ids, so React keys stay unique. */
function withIndex(v: unknown, i: number): unknown {
  if (!i || !v || typeof v !== 'object' || Array.isArray(v)) return v
  const o = { ...(v as Record<string, unknown>) }
  for (const [k, val] of Object.entries(o)) {
    if (typeof val === 'number' && (k === 'id' || k.endsWith('_id'))) o[k] = val + 1
    if (typeof val === 'string' && (k === 'name' || k === 'key' || k === 'label')) o[k] = `${val} 2`
    if (typeof val === 'string' && /^[0-9a-f]{64}$/.test(val)) o[k] = 'cd'.repeat(32)
  }
  return o
}

function match(path: string, method: string): Op | undefined {
  for (const [tpl, ops] of Object.entries(doc.paths)) {
    const re = new RegExp(`^${tpl.replace(/\{[^}]+\}/g, '[^/]+')}$`)
    if (re.test(path)) return ops[method]
  }
  return undefined
}

/** What the fake API answers for a request, to build an override on (`{ ...fakeFor('GET', '/settings'), can_edit: true }`). */
export function fakeFor(method: string, path: string): Record<string, unknown> {
  const op = match(path, method.toLowerCase())
  const ok = Object.entries(op?.responses ?? {}).find(([code]) => code.startsWith('2'))
  return fake(ok?.[1].content?.['application/json']?.schema) as Record<string, unknown>
}

export type Overrides = Record<string, unknown | ((body: unknown) => unknown)>

/** Replace fetch: API calls answer from the contract (or `overrides`, keyed "GET /path"), the session is signed in,
 * anything else is a 404. Returns the mock so tests can see what was sent. */
export function installFakeApi(overrides: Overrides = {}) {
  const calls: { method: string; path: string; body: unknown }[] = []
  const fn = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const req = input instanceof Request ? input : new Request(String(input), init)
    const url = new URL(req.url)
    const method = req.method.toUpperCase()
    let body: unknown = null
    try {
      body = method === 'GET' ? null : await req.clone().json()
    } catch {
      body = null
    }
    if (url.pathname.startsWith('/_allauth/')) {
      return json({ data: { user: { id: 1, username: 'admin' } } })
    }
    const path = url.pathname.replace(/^\/api\/v1/, '')
    calls.push({ method, path, body })
    const key = `${method} ${path}`
    if (key in overrides) {
      const o = overrides[key]
      return json(typeof o === 'function' ? (o as (b: unknown) => unknown)(body) : o)
    }
    const op = match(path, method.toLowerCase())
    if (!op) return json({ code: 'not_found', message: 'Not found.' }, 404)
    const ok = Object.entries(op.responses ?? {}).find(([code]) => code.startsWith('2'))
    const schema = ok?.[1].content?.['application/json']?.schema
    return json(schema ? fake(schema) : null)
  })
  ;(globalThis as { testFetch?: typeof fetch }).testFetch = fn as unknown as typeof fetch
  return { fetch: fn, calls }
}

function json(data: unknown, status = 200) {
  return new Response(JSON.stringify(data), { status, headers: { 'Content-Type': 'application/json' } })
}
