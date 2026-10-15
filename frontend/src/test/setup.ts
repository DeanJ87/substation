import '@testing-library/jest-dom/vitest'

// Browser APIs jsdom lacks, as inert stand-ins so components that observe size or visibility can mount
class Observer {
  observe() {}
  unobserve() {}
  disconnect() {}
  takeRecords() {
    return []
  }
}
globalThis.ResizeObserver ??= Observer as unknown as typeof ResizeObserver
globalThis.IntersectionObserver ??= Observer as unknown as typeof IntersectionObserver
window.matchMedia ??= ((query: string) => ({
  matches: false,
  media: query,
  onchange: null,
  addListener() {},
  removeListener() {},
  addEventListener() {},
  removeEventListener() {},
  dispatchEvent: () => false,
})) as typeof window.matchMedia
window.scrollTo = () => {}
Element.prototype.scrollIntoView ??= () => {}

// The API client keeps the fetch and Request it was created with, so both are installed before any module loads:
// Request resolves the client's relative URLs as a browser would, and fetch passes to whatever a test installs
// (fakeApi.ts), or fails plainly if none did.
const BrowserRequest = globalThis.Request
globalThis.Request = class extends BrowserRequest {
  constructor(input: RequestInfo | URL, init?: RequestInit) {
    super(typeof input === 'string' && input.startsWith('/') ? `http://localhost${input}` : input, init)
  }
} as typeof Request
const holder = globalThis as { testFetch?: typeof fetch }
globalThis.fetch = ((input: RequestInfo | URL, init?: RequestInit) =>
  holder.testFetch
    ? holder.testFetch(input, init)
    : Promise.reject(new Error(`No fake API installed for ${String(input)}`))) as typeof fetch
