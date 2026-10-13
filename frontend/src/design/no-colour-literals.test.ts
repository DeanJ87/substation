// Brand rule 007-DR-01: feature, component and route styles take colour only from --sst-* tokens, so the three
// themes (and night vision's no-green/blue/white rule) hold everywhere.
import { describe, expect, it } from 'vitest'

const sheets = import.meta.glob<string>(
  ['../features/**/*.css', '../components/**/*.css', '../routes/**/*.css'],
  {
    query: '?raw',
    import: 'default',
    eager: true,
  },
)

describe('colour tokens', () => {
  it('feature, component and route CSS has no colour literals', () => {
    expect(Object.keys(sheets).length).toBeGreaterThan(5)
    const offenders = Object.entries(sheets).flatMap(([file, css]) =>
      css
        .split('\n')
        .map((line, i) => ({ file, n: i + 1, line: line.replace(/\/\*.*?\*\//g, '') }))
        .filter((x) => /#[0-9a-f]{3,8}\b|rgba?\(|hsla?\(/i.test(x.line))
        .map((x) => `${x.file}:${x.n} ${x.line.trim()}`),
    )
    expect(offenders).toEqual([])
  })
})
