// Sign-in through django-allauth headless (browser client: session cookie + CSRF).
import { csrfToken } from './csrf'

const BASE = '/_allauth/browser/v1'

export interface SessionUser {
  id: number
  username: string
  email?: string
}

async function call(path: string, init: RequestInit = {}): Promise<Response> {
  const headers = new Headers(init.headers)
  headers.set('Content-Type', 'application/json')
  if (init.method && init.method !== 'GET') headers.set('X-CSRFToken', csrfToken())
  return fetch(BASE + path, { ...init, headers, credentials: 'same-origin' })
}

/** Current user, or null when signed out. Also makes Django set the CSRF cookie. */
export async function getSession(): Promise<SessionUser | null> {
  const r = await call('/auth/session')
  if (r.status === 401) return null
  if (!r.ok) throw new Error(`Session check failed (${r.status}).`)
  const body = await r.json()
  return body.data.user as SessionUser
}

export async function signIn(login: string, password: string): Promise<SessionUser> {
  await getSession() // ensures the CSRF cookie exists
  const key = login.includes('@') ? 'email' : 'username'
  const r = await call('/auth/login', { method: 'POST', body: JSON.stringify({ [key]: login, password }) })
  const body = await r.json().catch(() => ({}))
  if (r.ok) return body.data.user as SessionUser
  // a refused request isn't a wrong password: say which (2026-10-11, the NAS address wasn't trusted yet)
  const message =
    body?.errors?.[0]?.message ??
    (r.status === 401
      ? 'Two-step sign-in required.'
      : r.status === 403
        ? "The server refused the sign-in from this address (check the site's trusted origins)."
        : r.status >= 500
          ? `The server failed (${r.status}). Try again shortly.`
          : 'Wrong username or password.')
  throw new Error(message)
}

export async function signOut(): Promise<void> {
  await call('/auth/session', { method: 'DELETE' })
}
