import { cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { type Sky, SkyTable, SkyTracks, SkyView } from './SkyView'

const t = (h: number, m = 0) => `2026-10-11T${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}:00Z`

function sky(): Sky {
  const sub = (i: number, track: number, time: string, alt: number, az: number, verdict = 'accept') => ({
    sha256: String(i).padStart(64, '0'),
    file: `Light_${i}.fits`,
    time,
    exptime_s: 300,
    alt,
    az,
    source: 'solve',
    track,
    segment: 0,
    verdict,
    weight: verdict === 'down' ? 0.5 : 1,
    fwhm_arcsec: 2.4,
    fwhm_px: 1.6,
  })
  return {
    date: '2026-10-11',
    site_key: 'home',
    lat: 54.995,
    lon: -1.663,
    start: t(20),
    end: t(23),
    twilight: { sunset: t(17, 20), dusk: t(19, 20), dawn: t(5, 0), sunrise: t(7, 10) },
    moon: {
      illumination: 0.02,
      points: [
        { time: t(20), alt: -10, az: 80 },
        { time: t(23), alt: -5, az: 100 },
      ],
    },
    targets: [
      {
        key: 'c1',
        name: 'North America Nebula',
        collection_id: 1,
        curve: [
          { time: t(20), alt: 70, az: 150 },
          { time: t(23), alt: 60, az: 260 },
        ],
      },
      {
        key: 'c2',
        name: 'Heart Nebula',
        collection_id: 2,
        curve: [
          { time: t(20), alt: 40, az: 50 },
          { time: t(23), alt: 65, az: 80 },
        ],
      },
    ],
    rigs: [
      { key: 'r1', name: 'Askar 71F + ATR2600M' },
      { key: 'r2', name: 'Sony A7 III' },
    ],
    tracks: [
      {
        target: 'c1',
        rig: 'r1',
        dataset_id: 10,
        filter: 'OIII',
        label: 'North America Nebula · OIII',
        first: t(20, 30),
        last: t(21),
        subs: 2,
        integration_s: 600,
      },
      {
        target: 'c2',
        rig: 'r2',
        dataset_id: 11,
        filter: 'L',
        label: 'Heart Nebula · L',
        first: t(21, 30),
        last: t(22),
        subs: 2,
        integration_s: 600,
      },
    ],
    subs: [
      sub(1, 0, t(20, 30), 68, 170),
      sub(2, 0, t(21), 67, 190, 'down'),
      sub(3, 1, t(21, 30), 50, 60, 'reject'),
      sub(4, 1, t(22), 55, 65),
    ],
    unplaced: [{ sha256: 'f'.repeat(64), file: 'Light_9.fits', reason: 'No time recorded.' }],
  }
}

afterEach(cleanup)

// the dome's marks: coloured paths in the sky drawing (not the key's swatches)
const marks = (c: HTMLElement) => c.querySelectorAll('svg[role="img"] path[class*="mark"]')

describe('the sky dome', () => {
  it('marks every sub, joins each track, and opens a sub when its mark is chosen', () => {
    const open = vi.fn()
    const { container } = render(<SkyView sky={sky()} onOpen={open} />)
    expect(screen.getByRole('img', { name: /4 subs of 2 targets/ })).toBeInTheDocument()
    // two track lines and four marks, each with its target's colour
    const coloured = Array.from(marks(container))
    expect(coloured.filter((p) => p.getAttribute('style')?.includes('fill: var(--sst-panel)'))).toHaveLength(
      1,
    ) // the reject is hollow
    fireEvent.click(coloured[coloured.length - 1])
    expect(open).toHaveBeenCalled()
  })

  it('shows a sub’s details on hover', () => {
    const { container } = render(<SkyView sky={sky()} onOpen={() => {}} />)
    const mark = Array.from(marks(container)).find((p) => p.getAttribute('class')?.includes('mark'))!
    fireEvent.mouseEnter(mark)
    const tip = screen.getByRole('status')
    expect(within(tip).getByText(/Altitude \d+°, azimuth \d+°/)).toBeInTheDocument()
    fireEvent.mouseLeave(mark)
    expect(screen.queryByRole('status')).toBeNull()
  })

  it('brings one target into focus at a time; a rig row hides its marks', () => {
    const { container } = render(<SkyView sky={sky()} onOpen={() => {}} />)
    const before = marks(container).length
    const targets = sky().targets.map((x) => screen.getByRole('button', { name: new RegExp(x.name) }))
    expect(targets.filter((b) => b.getAttribute('aria-pressed') === 'true')).toHaveLength(1)
    const other = targets.find((b) => b.getAttribute('aria-pressed') === 'false')!
    fireEvent.click(other)
    expect(other).toHaveAttribute('aria-pressed', 'true')
    expect(targets.filter((b) => b.getAttribute('aria-pressed') === 'true')).toHaveLength(1)
    expect(marks(container).length).toBe(before) // the others stay, faint
    const sony = screen.getByRole('button', { name: /Sony A7 III/ })
    fireEvent.click(sony)
    expect(sony).toHaveAttribute('aria-pressed', 'false')
    expect(marks(container).length).toBeLessThan(before)
  })

  it('turns and zooms the dome, and resets', () => {
    render(<SkyView sky={sky()} onOpen={() => {}} />)
    const start = screen.getByText(/looking .* above/).textContent ?? ''
    expect(screen.queryByRole('button', { name: 'Reset view' })).toBeNull()
    fireEvent.click(screen.getByRole('button', { name: 'Turn right' }))
    expect(screen.getByText(/looking .* above/).textContent).not.toBe(start)
    fireEvent.click(screen.getByRole('button', { name: 'Zoom in' }))
    expect(screen.getByRole('button', { name: 'Zoom out' })).toBeEnabled()
    fireEvent.click(screen.getByRole('button', { name: 'Reset view' }))
    expect(screen.getByText(/looking .* above/).textContent).toBe(start)
    expect(screen.getByRole('button', { name: 'Zoom out' })).toBeDisabled()
  })

  it('replays the night with the slider', () => {
    const { container } = render(<SkyView sky={sky()} onOpen={() => {}} />)
    const slider = screen.getByRole('slider', { name: 'Time through the night' })
    expect(screen.getByText('Whole night')).toBeInTheDocument()
    fireEvent.change(slider, { target: { value: String(Date.parse(t(20, 45))) } })
    expect(marks(container).length).toBe(1)
    expect(slider).toHaveAttribute('aria-valuetext', expect.stringMatching(/\d\d:\d\d/))
  })

  it('steps through the night when reduced motion is asked for', () => {
    vi.useFakeTimers()
    const mm = vi.spyOn(window, 'matchMedia').mockReturnValue({ matches: true } as MediaQueryList)
    const { container } = render(<SkyView sky={sky()} onOpen={() => {}} />)
    fireEvent.click(screen.getByRole('button', { name: 'Play the night' }))
    expect(screen.getByRole('button', { name: 'Pause' })).toHaveAttribute('aria-pressed', 'true')
    vi.advanceTimersByTime(700 * 2)
    expect(marks(container).length).toBeLessThan(4)
    mm.mockRestore()
    vi.useRealTimers()
  })

  it('draws the focused target’s camera frame where it pointed, and says so', () => {
    const withFov = sky()
    withFov.tracks[0].fov = { ra_deg: 314.75, dec_deg: 44.3, w_deg: 3.2, h_deg: 2.1, rotation_deg: 90 }
    const { container } = render(<SkyView sky={withFov} onOpen={() => {}} />)
    const frame = container.querySelector('svg[role="img"] g[class*="frame"]')!
    expect(frame.querySelector('title')?.textContent).toMatch(/Askar 71F \+ ATR2600M’s frame, 3\.2° × 2\.1°/)
    expect(frame.querySelectorAll('path')).toHaveLength(2)
    // the explanation sits behind the frame's ? (C13)
    fireEvent.click(screen.getByRole('button', { name: 'Help: Camera frame' }))
    expect(screen.getByText(/camera’s frame from its plate solve/)).toHaveTextContent(/middle of the night/)
    // another target in focus: its rig has no solve, so no frame
    fireEvent.click(screen.getByRole('button', { name: /Heart Nebula/ }))
    expect(container.querySelector('g[class*="frame"]')).toBeNull()
  })

  it('says why nothing can be placed', () => {
    const empty = { ...sky(), subs: [], tracks: [] }
    render(<SkyView sky={empty} onOpen={() => {}} />)
    expect(screen.getByText(/can be placed on the sky: No time recorded/)).toBeInTheDocument()
  })

  it('tells the moon, darkness and what couldn’t be placed', () => {
    render(<SkyView sky={sky()} onOpen={() => {}} />)
    expect(screen.getByText('2% lit · below the horizon')).toBeInTheDocument()
    expect(screen.getByText(/1 sub: No time recorded/)).toBeInTheDocument()
  })
})

describe('the sky in words', () => {
  it('lists each track with its rig, times and integration', () => {
    render(<SkyTracks sky={sky()} />)
    const list = screen.getByRole('list', { name: 'Tracks' })
    expect(within(list).getByText('Heart Nebula · L')).toBeInTheDocument()
    expect(within(list).getByText(/Sony A7 III/)).toBeInTheDocument()
  })

  it('tabulates every sub, and each row opens the viewer', () => {
    const open = vi.fn()
    render(<SkyTable sky={sky()} onOpen={open} />)
    const rows = screen.getAllByRole('row')
    expect(rows).toHaveLength(5)
    expect(within(rows[3]).getByText('Rejected')).toBeInTheDocument()
    fireEvent.click(within(rows[1]).getByRole('button'))
    expect(open).toHaveBeenCalledWith('1'.padStart(64, '0'))
  })
})
