import { describe, expect, it } from 'vitest'
import { mapPath } from './FilePath'

describe('mapPath', () => {
  const maps = [
    { from: '/data/library/organised', to: 'Z:\\Photography\\Deep Sky\\Organised' },
    { from: '/data/library', to: '/Volumes/Photography' },
  ]
  it('uses the longest matching prefix and Windows separators for a drive letter', () => {
    expect(mapPath('/data/library/organised/M81/master.fit', maps)).toBe(
      'Z:\\Photography\\Deep Sky\\Organised\\M81\\master.fit',
    )
  })
  it('keeps forward slashes for a POSIX target', () => {
    expect(mapPath('/data/library/archive/x.fits', maps)).toBe('/Volumes/Photography/archive/x.fits')
  })
  it('leaves unmapped paths, and near-miss prefixes, alone', () => {
    expect(mapPath('/data/substation/stacks/m.fit', maps)).toBe('/data/substation/stacks/m.fit')
    expect(mapPath('/data/library/organisedX/a', [maps[0]])).toBe('/data/library/organisedX/a')
  })
})
