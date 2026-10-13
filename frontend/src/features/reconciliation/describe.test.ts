import { describe, expect, it } from 'vitest'
import { globMatch, groupPlace, likeGlob, listText, needLine, type Example } from './describe'

const ex = (o: Partial<Example>): Example =>
  ({
    sha256: 'a'.repeat(64),
    frame_type: 'light',
    library_id: 1,
    library: 'Astro',
    folder: 'x',
    file_name: 'f.fits',
    needs: [],
    ...o,
  }) as Example

describe('reconciliation wording', () => {
  it('lists fields as a sentence', () => {
    expect(listText(['gain'])).toBe('gain')
    expect(listText(['gain', 'offset', 'temperature'])).toBe('gain, offset and temperature')
  })

  it('says what a master needs and why', () => {
    const m = ex({ frame_type: 'master_dark', needs: ['gain', 'offset'], set_temp_c: -20 })
    expect(needLine('master_metadata', 'gain', m)).toBe(
      'Needs gain and offset so it can be matched to lights shot at −20 °C.',
    )
    expect(needLine('missing_field', 'filter', ex({ needs: ['exptime', 'filter'] }))).toBe(
      'Needs filter and exposure before it can join a session.',
    )
  })

  it('makes a safe glob for files like this', () => {
    const g = likeGlob('2026-09-28_20-05-02_Halpha_-20.00_600.00s_0027.xisf')
    expect(g).toBe('*_Halpha_-*s_*.xisf')
    expect(globMatch(g!, '2026-10-01_21-00-00_Halpha_-10.00_300.00s_0001.xisf')).toBe(true)
    expect(globMatch(g!, '2026-10-01_21-00-00_OIII_-10.00_300.00s_0001.xisf')).toBe(false)
    expect(likeGlob('0001.fits')).toBeNull()
    expect(globMatch(likeGlob('dark[1].fits')!, 'dark[7].fits')).toBe(true)
  })

  it('reads the place from a group key', () => {
    expect(groupPlace('missing_field|filter|3|LIGHT/a|b')).toEqual({ library: '3', folder: 'LIGHT/a|b' })
  })
})
