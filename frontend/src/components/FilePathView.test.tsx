import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { installFakeApi } from '../test/fakeApi'
import { FilePath, fileMode, localPathMap, saveFileMode, saveLocalPathMap, shareFolderUrl } from './FilePath'

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

describe('Open in Finder (2026-10-17)', () => {
  const unc = [{ from: '/data/substation', to: '\\\\nas\\Station' }]
  it('turns a share mapping into the smb:// link of the file’s folder', () => {
    expect(shareFolderUrl('/data/substation/masters/M 42/master.fit', unc)).toBe(
      'smb://nas/Station/masters/M%2042/',
    )
    expect(shareFolderUrl('/data/library/sub.fit', unc)).toBeNull() // no share mapping reaches it
    expect(shareFolderUrl('/data/substation/x.fit', [{ from: '/data/substation', to: 'Z:\\' }])).toBeNull()
  })
  it('shows the link on a Mac only', async () => {
    installFakeApi({ 'GET /settings': { processing: { paths: { map: unc } } } })
    const ua = vi
      .spyOn(navigator, 'userAgent', 'get')
      .mockReturnValue('Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0)')
    show('/data/substation/masters/master.fit')
    expect(await screen.findByRole('link', { name: 'Open in Finder' })).toHaveAttribute(
      'href',
      'smb://nas/Station/masters/',
    )
    cleanup()
    ua.mockReturnValue('Mozilla/5.0 (Windows NT 10.0; Win64; x64)')
    show('/data/substation/masters/master.fit')
    expect(await screen.findByRole('button', { name: 'Copy path' })).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'Open in Finder' })).toBeNull()
    ua.mockRestore()
  })
})
