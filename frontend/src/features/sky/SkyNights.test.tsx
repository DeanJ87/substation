import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { api } from '../../api/client'
import { type Nights, SkyNights, TargetSky, ageOpacity, facingOf, filtersOf, monthTicks } from './SkyNights'

const at = (d: string, h: number, m = 0) =>
  `${d}T${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}:00Z`

function nights(): Nights {
  const dates = ['2026-08-20', '2026-09-14', '2026-10-11']
  const sub = (
    i: number,
    night: number,
    h: number,
    alt: number,
    az: number,
    rig = 'r1',
    verdict = 'accept',
  ) => ({
    sha256: String(i).padStart(64, '0'),
    time: at(dates[night], h),
    alt,
    az,
    night,
    dataset_id: 10,
    segment: 0,
    rig,
    verdict,
    filter: i % 2 ? 'Hα' : 'OIII',
    exptime_s: 300,
  })
  return {
    name: 'North America Nebula',
    site_key: 'home',
    lat: 54.995,
    lon: -1.663,
    places: [
      { key: 'home', lat: 54.995, lon: -1.663, subs: 6, nights: 3 },
      { key: 'away', lat: 55.5, lon: -2.0, subs: 1, nights: 1 },
    ],
    nights: dates.map((d, i) => ({
      date: d,
      site_key: 'home',
      subs: 2,
      integration_s: 600,
      first: at(d, 21),
      last: at(d, 22),
      alt_min: 50 + i,
      alt_max: 70 + i,
      alt_mid: 60 + i,
    })),
    rigs: [
      { key: 'r1', name: 'Askar 71F + ATR2600M' },
      { key: 'r2', name: 'Sony A7 III' },
    ],
    subs: [
      sub(1, 0, 21, 60, 150),
      sub(2, 0, 22, 62, 170),
      sub(3, 1, 21, 64, 160, 'r2'),
      sub(4, 1, 22, 66, 180, 'r2', 'reject'),
      sub(5, 2, 21, 68, 165),
      sub(6, 2, 22, 70, 190),
    ],
    unplaced: 1,
    fov: { ra_deg: 314.75, dec_deg: 44.3, w_deg: 3.2, h_deg: 2.1, rotation_deg: 0 },
  }
}

afterEach(cleanup)

const tracks = (c: HTMLElement) =>
  Array.from(c.querySelectorAll<SVGPathElement>('svg[role="img"] path[class*="track"]'))

describe('a target across its nights (spec 015 N7)', () => {
  it('stacks every night on one dome, the latest brightest', () => {
    const { container } = render(<SkyNights sky={nights()} onSite={() => {}} />)
    expect(
      screen.getByRole('img', { name: /6 subs over 3 nights, the latest brightest/ }),
    ).toBeInTheDocument()
    const lines = tracks(container)
    expect(lines).toHaveLength(3)
    const op = lines.map((l) => Number(l.style.opacity))
    expect(op[op.length - 1]).toBe(1) // drawn last, on top
    expect(Math.min(...op)).toBeCloseTo(0.25)
    expect(container.querySelector('g[class*="frame"] title')?.textContent).toMatch(/3\.2° × 2\.1°/)
  })

  it('lists the nights newest first, and choosing one brings it forward', () => {
    const { container } = render(<SkyNights sky={nights()} onSite={() => {}} />)
    const rows = within(screen.getByRole('heading', { name: 'Nights' }).parentElement!).getAllByRole('button')
    expect(rows[0]).toHaveTextContent('Night 3 of 3')
    expect(rows[2]).toHaveTextContent('Night 1 of 3')
    fireEvent.click(rows[2])
    expect(rows[2]).toHaveAttribute('aria-pressed', 'true')
    fireEvent.mouseLeave(rows[2])
    const op = tracks(container).map((l) => Number(l.style.opacity))
    expect(op.filter((o) => o === 1)).toHaveLength(1)
    expect(op.filter((o) => o === 0.1)).toHaveLength(2)
    expect(screen.getByText(/in the middle of that night/)).toBeInTheDocument()
    fireEvent.click(rows[2])
    expect(rows[2]).toHaveAttribute('aria-pressed', 'false')
  })

  it('names each rig’s shape, offers the other places, and counts what couldn’t be placed', () => {
    const onSite = vi.fn()
    render(<SkyNights sky={nights()} onSite={onSite} />)
    expect(screen.getByText(/Circles: Askar 71F \+ ATR2600M; Squares: Sony A7 III/)).toBeInTheDocument()
    expect(screen.getByText(/1 sub couldn’t be placed/)).toBeInTheDocument()
    fireEvent.change(screen.getByRole('combobox', { name: /From/ }), { target: { value: 'away' } })
    expect(onSite).toHaveBeenCalledWith('away')
  })

  it('draws the altitudes each night spanned along the dates', () => {
    const { container } = render(<SkyNights sky={nights()} onSite={() => {}} />)
    const strip = screen.getByRole('img', { name: /altitudes each night’s subs spanned/ })
    expect(strip.querySelectorAll('line[class*="stripBar"]')).toHaveLength(3)
    expect(within(container).getByText('Altitude over the dates')).toBeInTheDocument()
  })

  it('says when nothing can be placed', () => {
    render(<SkyNights sky={{ ...nights(), subs: [], places: [] }} onSite={() => {}} />)
    expect(screen.getByText(/No subs with a known place/)).toBeInTheDocument()
  })

  it('faces the target to start with', () => {
    expect(facingOf([{ az: 350 }, { az: 15 }])).toBe(0)
    expect(facingOf([{ az: 170 }])).toBe(180)
    expect(facingOf([])).toBe(180)
    render(<SkyNights sky={nights()} onSite={() => {}} />)
    // the fixture's subs sit at 60–70° up, so the view starts higher than the usual 32°
    expect(screen.getByText(/Facing south · 62° up/)).toBeInTheDocument()
  })

  it('fades older nights evenly and marks the months', () => {
    expect(ageOpacity(0, 1)).toBe(1)
    expect(ageOpacity(0, 3)).toBeCloseTo(0.25)
    expect(ageOpacity(2, 3)).toBe(1)
    const ticks = monthTicks(Date.parse('2026-08-19T00:00:00Z'), Date.parse('2026-10-12T00:00:00Z'))
    expect(ticks.map((t) => new Date(t).toISOString().slice(0, 10))).toEqual(['2026-09-01', '2026-10-01'])
    expect(monthTicks(Date.parse('2026-10-02T00:00:00Z'), Date.parse('2026-10-04T00:00:00Z'))).toHaveLength(1)
  })

  it('loads the dataset’s sky from the API', async () => {
    const get = vi
      .spyOn(api, 'GET')
      .mockResolvedValue({ data: nights(), response: new Response('{}') } as never)
    render(
      <QueryClientProvider client={new QueryClient()}>
        <TargetSky kind="dataset" id={10} />
      </QueryClientProvider>,
    )
    expect(screen.getByText(/Working out where each sub was/)).toBeInTheDocument()
    await waitFor(() => expect(screen.getByRole('heading', { name: 'Nights' })).toBeInTheDocument())
    expect(get).toHaveBeenCalledWith('/datasets/{dataset_id}/sky', {
      params: { path: { dataset_id: 10 }, query: { site: undefined } },
    })
    get.mockRestore()
  })
})

describe('filters on the sky (2026-10-16)', () => {
  it('colours each frame by its filter and lets a filter be hidden', () => {
    const { container } = render(<SkyNights sky={nights()} onSite={() => {}} />)
    const marks = () => container.querySelectorAll('path[style*="--sst-filter"]').length
    const before = marks()
    expect(before).toBeGreaterThan(0)
    const ha = screen.getByRole('button', { name: /^Hα/ })
    expect(ha).toHaveAttribute('aria-pressed', 'true')
    fireEvent.click(ha)
    expect(ha).toHaveAttribute('aria-pressed', 'false')
    expect(marks()).toBeLessThan(before)
  })
  it('orders broadband before narrowband', () => {
    expect(filtersOf([{ filter: 'OIII' }, { filter: 'L' }, { filter: 'Hα' }, { filter: 'R' }])).toEqual([
      'L',
      'R',
      'Hα',
      'OIII',
    ])
  })
})
