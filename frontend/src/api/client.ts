// Typed API client generated from specs/001-ingest-catalogue/contracts/openapi.yaml (`npm run api:gen`).
// Session cookie auth; unsafe methods carry the CSRF token Django sets on the session check.
import createClient, { type Middleware } from 'openapi-fetch'
import { csrfToken, UNSAFE } from './csrf'
import type { paths } from './schema'

export class ApiError extends Error {
  status: number
  code: string
  constructor(status: number, code: string, message: string) {
    super(message)
    this.status = status
    this.code = code
  }
}

const csrf: Middleware = {
  onRequest({ request }) {
    if (UNSAFE.has(request.method)) request.headers.set('X-CSRFToken', csrfToken())
    return request
  },
}

export const api = createClient<paths>({ baseUrl: '/api/v1', credentials: 'same-origin' })
api.use(csrf)

/** Unwrap an openapi-fetch result, turning API errors into ApiError with the server's plain-English message. */
export function unwrap<T>(res: { data?: T; error?: unknown; response: Response }): T {
  if (res.error !== undefined || !res.response.ok) {
    const e = (res.error ?? {}) as { code?: string; message?: string }
    throw new ApiError(
      res.response.status,
      e.code ?? 'error',
      e.message ?? `Request failed (${res.response.status}).`,
    )
  }
  return res.data as T
}
