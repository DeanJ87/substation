// 2026-10-24: a stitched master's post-processing shows on its card (010-DR-28), a run takes the steps chosen for
// it (010-DR-29), Stitch mosaic and Stack together take chosen filters (004-DR-34), and a master can be drizzled
// ×2 or binned 2×2 (004-DR-35).
import { cleanup, fireEvent, screen, waitFor, within } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'
import { renderRoute } from '../../test/renderRoute'
import { fakeFor } from '../../test/fakeApi'

afterEach(cleanup)

const fakeCombined = (fakeFor('get', '/collections/1/combined') as { combined: object[] }).combined[0]
const masterRow = {
  id: 1,
  dataset_id: 11,
  dataset: 'Askar 71F · Hα · Panel 1',
  version: 1,
  state: 'current',
  sub_count: 10,
  integration_s: 36000,
  finished_at: null,
  has_preview: false,
  filter: 'Hα',
}
const STEPS = [
  {
    step: 'background',
    label: 'Background extracted',
    tool: 'GraXpert',
    on: true,
    available: true,
    reason: '',
  },
  {
    step: 'deconvolve',
    label: 'Deconvolved',
    tool: 'BlurXTerminator',
    on: true,
    available: true,
    reason: '',
  },
  { step: 'denoise', label: 'Denoised', tool: 'NoiseXTerminator', on: true, available: true, reason: '' },
  {
    step: 'starless',
    label: 'Starless',
    tool: 'StarXTerminator',
    on: false,
    available: false,
    reason: "RC-Astro isn't activated on this finisher.",
  },
]
const stage = (step: string, label: string, i: number, preview: boolean) => ({
  step,
  label,
  state: 'done',
  reason: '',
  tool: step === 'background' ? 'graxpert' : 'rc_astro',
  seconds: 300,
  params: {},
  preview: preview ? `/api/v1/combined/15/post/1/${i}/preview` : null,
  full: `/api/v1/combined/15/post/1/${i}/full`,
  tool_label: step === 'background' ? 'GraXpert' : 'BlurXTerminator',
  stats: {},
  file_path: `/data/stacks/collections/col1/combined_p1_Hα_v1_post-1/step${i}_${step}/x.fits`,
  download: `/api/v1/combined/15/post/1/${i}/download`,
})
// CombinedMaster 15 as production returned it: a helper's run; the background stage has its 100% view but no preview
const POST = {
  enabled: true,
  queued: false,
  helper_online: false,
  helper_host: 'studio-mac',
  helper_seen_at: null,
  steps: STEPS,
  runs: [
    {
      run: 1,
      started_at: '2026-10-24T01:00:00Z',
      finished_at: '2026-10-24T02:10:00Z',
      original_stats: {},
      chosen: null,
      helper: 'studio-mac',
      stages: [
        stage('background', 'Background extracted', 0, false),
        stage('deconvolve', 'Deconvolved', 1, true),
        {
          ...stage('denoise', 'Denoised', 2, false),
          state: 'skipped',
          full: null,
          file_path: '',
          download: null,
          reason: "RC-Astro isn't activated.",
        },
      ],
    },
  ],
}
const PLAN = {
  ...fakeFor('get', '/collections/1/combined'),
  method: 'stitch',
  default_method: 'stitch',
  methods: ['stitch', 'stack'],
  reference: 1,
  reference_label: 'Askar 71F · Hα · Panel 1',
  filters: {
    Hα: [
      {
        master: 1,
        dataset: 11,
        label: 'Askar 71F · Hα · Panel 1',
        version: 2,
        integration_s: 36000,
        subs: 60,
      },
      {
        master: 2,
        dataset: 12,
        label: 'Askar 71F · Hα · Panel 2',
        version: 1,
        integration_s: 18000,
        subs: 30,
        stale: true,
      },
    ],
    OIII: [
      {
        master: 3,
        dataset: 13,
        label: 'Askar 71F · OIII · Panel 1',
        version: 1,
        integration_s: 7200,
        subs: 12,
      },
    ],
  },
  left_out: [],
  notes: [],
  combined: [
    {
      ...fakeCombined,
      id: 16,
      filter: 'Hα',
      method: 'stitch',
      version: 2,
      state: 'failed',
      has_preview: false,
      error: 'Siril stopped',
    },
    {
      ...fakeCombined,
      id: 15,
      filter: 'Hα',
      method: 'stitch',
      version: 1,
      state: 'current',
      has_preview: true,
    },
  ],
}

async function open(more: Record<string, unknown> = {}) {
  const all = fakeFor('get', '/collections/1') as Record<string, unknown>
  return renderRoute('/collections/1?tab=masters', {
    'GET /collections/1': { ...all, masters: [masterRow] },
    'GET /collections/1/projects': { projects: [], unassigned: [], review: [] },
    'GET /collections/1/combined': PLAN,
    'GET /combined/15/post': POST,
    'GET /combined/16/post': { ...POST, runs: [] },
    ...more,
  })
}

describe('stitched masters on the Masters tab', { timeout: 20_000 }, () => {
  it('shows a finished run of the real report shape, a thumbnail per stage, beside a newer failed try', async () => {
    await open()
    const card = (await screen.findByText('Hα mosaic v1')).closest('article') as HTMLElement
    expect(await within(card).findByText('Post-processing')).toBeInTheDocument()
    expect(within(card).getByText(/run 1 · .* on studio-mac/)).toBeInTheDocument()
    // the stage with a preview has its thumbnail; the one without opens the 100% view by name
    // (the card's own picture is the latest processed stage too)
    expect(
      within(card)
        .getAllByRole('img', { name: 'Hα mosaic v1, Deconvolved' })
        .map((x) => x.getAttribute('src')),
    ).toContain('/api/v1/combined/15/post/1/1/preview?size=thumb')
    expect(
      within(card).getByRole('button', { name: 'Open Hα mosaic v1 · Background extracted at 100%' }),
    ).toHaveTextContent('View at 100%')
    expect(within(card).getByText("RC-Astro isn't activated.")).toBeInTheDocument()
    // the newer failed try is its own card; it doesn't hide the current one
    expect(screen.getByText('Hα mosaic v2')).toBeInTheDocument()
    // a stage opens the 100% view, with a tab per version
    fireEvent.click(within(card).getByRole('button', { name: 'Open Hα mosaic v1 · Deconvolved at 100%' }))
    const tabs = await screen.findByRole('tablist', { name: 'Versions' })
    expect(within(tabs).getByRole('tab', { name: /Deconvolved|BlurXTerminator/ })).toHaveAttribute(
      'aria-selected',
      'true',
    )
  })

  it('runs post-processing again with the steps chosen for this run', async () => {
    const { api } = await open({ 'POST /combined/15/post': { ...POST, queued: true } })
    const card = (await screen.findByText('Hα mosaic v1')).closest('article') as HTMLElement
    fireEvent.click(await within(card).findByRole('button', { name: 'Run again…' }))
    const dialog = await screen.findByRole('dialog', { name: 'Post-process Hα mosaic v1' })
    // Settings' selection to start with; a step whose tool isn't ready can't be chosen, and says why
    expect(within(dialog).getByRole('checkbox', { name: /Background extracted/ })).toBeChecked()
    expect(within(dialog).getByRole('checkbox', { name: /Starless/ })).toBeDisabled()
    expect(within(dialog).getByText("RC-Astro isn't activated on this finisher.")).toBeInTheDocument()
    fireEvent.click(within(dialog).getByRole('checkbox', { name: /Deconvolved/ }))
    fireEvent.click(within(dialog).getByRole('checkbox', { name: /Denoised/ }))
    fireEvent.click(within(dialog).getByRole('button', { name: 'Run 1 step' }))
    await waitFor(() =>
      expect(api.calls).toContainEqual({
        method: 'POST',
        path: '/combined/15/post',
        body: { steps: ['background'] },
      }),
    )
  })

  it('says which steps a run was asked for', async () => {
    const run = { ...POST.runs[0], chosen: ['background', 'deconvolve'] }
    await open({ 'GET /combined/15/post': { ...POST, runs: [run] } })
    expect(
      await screen.findByText('Steps chosen for this run: Background extracted, Deconvolved'),
    ).toBeInTheDocument()
  })

  it('stitches the chosen filters only, showing what goes into each', async () => {
    const { api } = await open({ 'POST /collections/1/combined': [] })
    fireEvent.click(await screen.findByRole('button', { name: 'Stitch mosaic…' }))
    const dialog = await screen.findByRole('dialog', { name: 'Stitch mosaic' })
    const ha = within(dialog).getByRole('list', { name: 'Hα masters' })
    expect(within(ha).getByText('Askar 71F · Hα · Panel 2 · v1')).toBeInTheDocument()
    expect(within(ha).getByText('Older master')).toBeInTheDocument()
    expect(within(dialog).getByText(/canvas is drawn from every panel of every filter/)).toBeInTheDocument()
    expect(within(dialog).getByRole('button', { name: 'Stitch 2 filters' })).toBeInTheDocument()
    fireEvent.click(within(dialog).getByRole('checkbox', { name: /OIII/ }))
    fireEvent.click(within(dialog).getByRole('button', { name: 'Stitch Hα' }))
    await waitFor(() =>
      expect(api.calls).toContainEqual({
        method: 'POST',
        path: '/collections/1/combined',
        body: { filters: ['Hα'] },
      }),
    )
  })
})

describe('drizzle or bin a dataset master (004-DR-35)', { timeout: 20_000 }, () => {
  const stack = fakeFor('get', '/datasets/1/stacks') as unknown as Record<string, unknown>[]
  it('offers Normal, Drizzle ×2 and Bin 2×2, sends the choice and shows it on the card', async () => {
    const { api } = await renderRoute('/datasets/1?tab=masters', {
      'GET /datasets/1/stacks': [
        {
          ...stack[0],
          id: 7,
          version: 3,
          state: 'current',
          resolution: 'drizzle2',
          method: 'winsorised σ 3 · grade weights · Drizzle ×2',
        },
      ],
      'GET /stacks/7/post': { ...POST, runs: [] },
      'POST /datasets/1/stacks/preview': { ...fakeFor('post', '/datasets/1/stacks/preview'), subs: 40 },
      'POST /datasets/1/stacks': stack[0],
    })
    // on the version's card, beside its state (the option list has the same words)
    await waitFor(() =>
      expect(screen.getAllByText('Drizzle ×2').some((x) => x.tagName !== 'OPTION')).toBe(true),
    )
    const select = screen.getByRole('combobox', { name: /Resolution/ })
    expect(within(select).getByRole('option', { name: 'Normal' })).toBeInTheDocument()
    fireEvent.change(select, { target: { value: 'bin2' } })
    expect(screen.getByText(/half the width and height/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /Stack 40 subs/ }))
    await waitFor(() =>
      expect(
        api.calls.find((c) => c.method === 'POST' && c.path === '/datasets/1/stacks')?.body,
      ).toMatchObject({ options: { resolution: 'bin2' } }),
    )
  })

  it("a dataset master's post-processing takes chosen steps too", async () => {
    const { api } = await renderRoute('/datasets/1?tab=masters', {
      'GET /datasets/1/stacks': [{ ...stack[0], id: 7, version: 3, state: 'current', has_preview: true }],
      'GET /stacks/7/post': POST,
      'POST /stacks/7/post': { ...POST, queued: true },
    })
    fireEvent.click(await screen.findByRole('button', { name: 'Post-process again…' }))
    const dialog = await screen.findByRole('dialog', { name: 'Post-process Master v3' })
    fireEvent.click(within(dialog).getByRole('checkbox', { name: /Denoised/ }))
    fireEvent.click(within(dialog).getByRole('button', { name: 'Run 2 steps' }))
    await waitFor(() =>
      expect(api.calls).toContainEqual({
        method: 'POST',
        path: '/stacks/7/post',
        body: { steps: ['background', 'deconvolve'] },
      }),
    )
  })
})
