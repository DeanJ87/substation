// 006-DR-44: the collection's Masters tab narrowed to one filter, kept in the address; 004-DR-36: the 100% view's
// side panel says what a master holds.
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'
import { renderRoute } from '../../test/renderRoute'
import { fakeFor } from '../../test/fakeApi'
import { filterCounts, sameFilter } from './MasterFilters'
import { IntegrationPanel } from '../../components/CloseLook'

afterEach(cleanup)

const row = (id: number, filter: string, dataset: string) => ({
  id,
  dataset_id: 10 + id,
  dataset,
  version: 1,
  state: 'current',
  sub_count: 60,
  integration_s: 36000,
  finished_at: null,
  has_preview: true,
  filter,
})
const fakeCombined = (fakeFor('get', '/collections/1/combined') as { combined: object[] }).combined[0]
const PLAN = {
  ...fakeFor('get', '/collections/1/combined'),
  method: 'stitch',
  default_method: 'stitch',
  methods: ['stitch'],
  reference: 1,
  reference_label: 'Askar 71F · Hα · Panel 1',
  filters: {},
  left_out: [],
  notes: [],
  combined: [
    {
      ...fakeCombined,
      id: 15,
      filter: 'Hα',
      method: 'stitch',
      version: 1,
      state: 'current',
      has_preview: false,
    },
    {
      ...fakeCombined,
      id: 16,
      filter: 'OIII',
      method: 'stitch',
      version: 1,
      state: 'current',
      has_preview: false,
    },
  ],
}

async function open(url = '/collections/1?tab=masters') {
  const all = fakeFor('get', '/collections/1') as Record<string, unknown>
  return renderRoute(url, {
    'GET /collections/1': {
      ...all,
      masters: [
        row(1, 'Hα', 'Askar 71F · Hα · Panel 1'),
        row(2, 'Hα', 'Askar 71F · Hα · Panel 2'),
        row(3, 'OIII', 'Askar 71F · OIII · Panel 1'),
      ],
    },
    'GET /collections/1/projects': { projects: [], unassigned: [], review: [] },
    'GET /collections/1/combined': PLAN,
    'GET /combined/15/post': { ...fakeFor('get', '/combined/15/post'), runs: [] },
    'GET /combined/16/post': { ...fakeFor('get', '/combined/16/post'), runs: [] },
    'GET /stacks/2/view': {
      ready: true,
      full: '/media/full.jpg',
      inspector: '/media/insp.jpg',
      integration: { kind: 'master', filter: 'Hα', integration_s: 64200, subs: 214, sessions: 9, parts: [] },
    },
    'GET /stacks/2/post': { ...fakeFor('get', '/stacks/2/post'), runs: [] },
  })
}

describe('Masters tab filter chips', { timeout: 20_000 }, () => {
  it('counts dataset and stitched masters per filter, in the canonical order', () => {
    expect(filterCounts(['OIII', 'Ha', 'Hα', 'SII'])).toEqual([
      ['Hα', 2],
      ['OIII', 1],
      ['SII', 1],
    ])
    expect(filterCounts(['Hα'], 'SII')).toEqual([
      ['Hα', 1],
      ['SII', 0],
    ])
    expect(sameFilter('Ha', 'Hα')).toBe(true)
    expect(sameFilter('OIII', 'Hα')).toBe(false)
  })

  it('narrows both lists to one filter and keeps it in the address', async () => {
    const { router } = await open()
    const chips = await screen.findByRole('group', { name: 'Show masters of one filter' })
    await within(chips).findByRole('button', { name: /OIII.*2/ })
    expect(within(chips).getByRole('button', { name: /All.*5/ })).toHaveAttribute('aria-pressed', 'true')
    expect(within(chips).getByRole('button', { name: /Hα.*3/ })).toBeInTheDocument()
    expect(await screen.findByText('Hα mosaic v1')).toBeInTheDocument()
    fireEvent.click(within(chips).getByRole('button', { name: /OIII/ }))
    await waitFor(() => expect(router.state.location.search).toMatchObject({ filter: 'OIII' }))
    expect(screen.queryByText('Hα mosaic v1')).not.toBeInTheDocument()
    expect(screen.getByText('OIII mosaic v1')).toBeInTheDocument()
    expect(screen.getByText(/Askar 71F · OIII · Panel 1/)).toBeInTheDocument()
    expect(screen.queryByText(/Askar 71F · Hα · Panel 2/)).not.toBeInTheDocument()
  })

  it('opens on the filter in the address', async () => {
    await open('/collections/1?tab=masters&filter=Ha')
    const chips = await screen.findByRole('group', { name: 'Show masters of one filter' })
    expect(within(chips).getByRole('button', { name: /Hα/ })).toHaveAttribute('aria-pressed', 'true')
    expect(await screen.findByText(/Askar 71F · Hα · Panel 2/)).toBeInTheDocument()
    expect(screen.queryByText(/Askar 71F · OIII · Panel 1/)).not.toBeInTheDocument()
  })

  it("shows a master's integration beside it at 100%", async () => {
    await open()
    fireEvent.click(await screen.findByRole('button', { name: /Open Askar 71F · Hα · Panel 2 v1 at 100%/ }))
    const panel = await screen.findByRole('complementary', { name: 'Integration' })
    expect(panel).toHaveTextContent('17h 50m')
    expect(panel).toHaveTextContent('214 subs · 9 nights')
  })
})

describe('IntegrationPanel', () => {
  it('lists a mosaic by panel, dimming one left out', () => {
    render(
      <IntegrationPanel
        i={{
          kind: 'stitch',
          filter: 'Hα',
          integration_s: 10800,
          subs: 36,
          parts: [
            {
              label: 'Askar · Hα · Panel 1',
              filter: 'Hα',
              panel: 1,
              integration_s: 7200,
              subs: 24,
              used: true,
            },
            {
              label: 'Askar · Hα · Panel 2',
              filter: 'Hα',
              panel: 2,
              integration_s: 3600,
              subs: 12,
              used: true,
            },
            {
              label: 'Askar · Hα · Panel 3',
              filter: 'Hα',
              panel: 3,
              integration_s: 1800,
              subs: 6,
              used: false,
            },
          ],
        }}
      />,
    )
    const panel = screen.getByRole('complementary', { name: 'Integration' })
    expect(panel).toHaveTextContent('Total · Hα3h')
    expect(within(panel).getByText('Panels')).toBeInTheDocument()
    const items = within(panel).getAllByRole('listitem')
    expect(items.map((x) => x.textContent)).toEqual([
      'Panel 12h · 24 subsAskar · Hα · Panel 1',
      'Panel 21h · 12 subsAskar · Hα · Panel 2',
      'Panel 330m · 6 subsAskar · Hα · Panel 3',
    ])
    expect(panel).toHaveTextContent(/left out/)
  })
})
