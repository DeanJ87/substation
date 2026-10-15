import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { installFakeApi } from '../test/fakeApi'
import { FilePath, fileMode, localPathMap, saveFileMode, saveLocalPathMap } from './FilePath'

const SITE = { processing: { paths: { map: [{ from: '/data/library', to: '/Volumes/Photography' }] } } }

beforeEach(() => {
  localStorage.clear()
  installFakeApi({ 'GET /settings': SITE })
})
afterEach(cleanup)

function show(path: string, download?: string) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={qc}>
      <FilePath path={path} download={download} />
    </QueryClientProvider>,
  )
}

describe('this browser’s file settings', () => {
  it('open in place unless set to download', () => {
    expect(fileMode()).toBe('open')
    saveFileMode('download')
    expect(fileMode()).toBe('download')
  })
  it('keep only complete path mappings', () => {
    saveLocalPathMap([
      { from: '/data', to: 'Z:\\' },
      { from: '', to: '/x' },
    ])
    expect(localPathMap()).toEqual([{ from: '/data', to: 'Z:\\' }])
    localStorage.setItem('sst-path-map', 'not json')
    expect(localPathMap()).toEqual([])
  })
})

describe('FilePath', () => {
  it('shows the path as this machine sees it, with a copy button', async () => {
    show('/data/library/M42/Light/sub.fit', '/media/sub.fit')
    expect(await screen.findByText('/Volumes/Photography/M42/Light/sub.fit')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Copy path' })).toBeInTheDocument()
  })
  it('offers a download where no mapping reaches the file', async () => {
    show('/data/substation/stacks/master.fit', '/media/master.fit')
    expect(await screen.findByRole('link', { name: 'Download' })).toHaveAttribute('href', '/media/master.fit')
    expect(screen.getByText('master.fit')).toBeInTheDocument()
  })
  it('downloads everything when this browser is set to', async () => {
    saveFileMode('download')
    show('/data/library/M42/Light/sub.fit', '/media/sub.fit')
    expect(await screen.findByRole('link', { name: 'Download' })).toBeInTheDocument()
  })
  it('a browser’s own mapping wins over the site’s', async () => {
    saveLocalPathMap([{ from: '/data/library', to: 'Z:\\Photography' }])
    show('/data/library/M42/sub.fit')
    expect(await screen.findByText('Z:\\Photography\\M42\\sub.fit')).toBeInTheDocument()
  })
})
