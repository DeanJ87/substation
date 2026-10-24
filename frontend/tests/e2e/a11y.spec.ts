// T106, 007-DR-27, 007-DR-46: axe (WCAG 2.2 A and AA) on every route in the router, in dark, light and night
// vision, at desktop and phone widths; plus the sub viewer, the skip link and a dialog's keyboard contract.
import { AxeBuilder } from '@axe-core/playwright'
import { expect, test, type Page } from '@playwright/test'
import { signIn } from './helpers'

// each theme × width is its own test and only reads pages, so they run side by side (CI passes --workers=3)
test.describe.configure({ mode: 'parallel' })

const THEMES = ['dark', 'light', 'night'] as const
const WIDTHS = [1440, 400] as const
const TAGS = ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa']
// every route in routes/router.tsx without an id; /queue redirects to /activity
const SCREENS = [
  '/',
  '/finished',
  '/review',
  '/calibration',
  '/calibration/to-shoot',
  '/map',
  '/activity',
  '/bin',
  '/reconcile',
  '/settings',
]
// routes with an id: the first one each list page links to, when the stack has one
const FOUND: [from: string, link: string, extra: string[]][] = [
  ['/', 'a[href^="/collections/"]', ['?tab=datasets', '?tab=sessions', '?tab=masters', '?tab=sky']],
  ['/', 'a[href^="/datasets/"]', ['?tab=quality', '?tab=calibration', '?tab=masters']],
  ['/finished', 'a[href^="/finished/"]', []],
  ['/calibration', 'a[href^="/calibration/sets/"]', []],
  ['/activity', 'a[href^="/nights/"]', []],
  ['/review', 'a[href^="/subs/"]', []],
]

async function settle(page: Page) {
  await page.waitForLoadState('networkidle')
}

async function axe(page: Page, label: string, failures: string[], include?: string) {
  let b = new AxeBuilder({ page }).withTags(TAGS)
  // map tiles are pictures drawn by OpenStreetMap, outside SubStation's control
  b = include ? b.include(include) : b.exclude('.leaflet-tile-pane')
  const r = await b.analyze()
  for (const v of r.violations)
    failures.push(`${label}: ${v.id} (${v.nodes.length}) ${v.nodes[0]?.target.join(' ')} — ${v.help}`)
}

async function routes(page: Page): Promise<string[]> {
  const out = [...SCREENS]
  for (const [from, link, extra] of FOUND) {
    await page.goto(from)
    await settle(page)
    const a = page.locator(link).first()
    if (!(await a.count())) continue
    const href = (await a.getAttribute('href'))!.split('?')[0]
    out.push(href, ...extra.map((x) => href + x))
  }
  return [...new Set(out)]
}

for (const theme of THEMES)
  for (const width of WIDTHS) {
    test(`no accessibility violations in ${theme} at ${width}px`, async ({ page }) => {
      test.setTimeout(10 * 60_000)
      await page.setViewportSize({ width, height: 900 })
      await page.addInitScript((t) => localStorage.setItem('sst-theme', t), theme)
      const failures: string[] = []
      await page.goto('/sign-in')
      await axe(page, '/sign-in', failures)
      await signIn(page)
      for (const path of await routes(page)) {
        await page.goto(path)
        await settle(page)
        await axe(page, path, failures)
        if (/^\/datasets\/\d+$/.test(path) && width === 1440) {
          // the sub viewer opens as a modal over the grid (spec 012)
          const open = page.getByRole('button', { name: /^Open / }).first()
          if (await open.count()) {
            await open.click()
            await page.getByRole('dialog').waitFor({ timeout: 15_000 })
            await settle(page)
            await axe(page, `${path} sub`, failures, '[role=dialog]')
            await page.keyboard.press('Escape')
          }
        }
      }
      expect(failures).toEqual([])
    })
  }

test('the skip link is the first stop and a dialog keeps and returns focus', async ({ page }) => {
  await signIn(page)
  await page.goto('/')
  await settle(page)
  await page.keyboard.press('Tab')
  await expect(page.locator(':focus')).toHaveText('Skip to content')
  await page.keyboard.press('Enter')
  await expect(page.locator('main#main')).toBeFocused()
  const collection = page.locator('a[href^="/collections/"]').first()
  if (!(await collection.count())) return
  await page.goto((await collection.getAttribute('href'))!)
  await settle(page)
  const edit = page.getByRole('button', { name: 'Edit collection' })
  await edit.focus()
  await page.keyboard.press('Enter')
  await page.getByRole('dialog').waitFor()
  for (let i = 0; i < 15; i++) {
    await page.keyboard.press('Tab')
    expect(await page.evaluate(() => !!document.activeElement?.closest('[role=dialog]'))).toBe(true)
  }
  await page.keyboard.press('Escape')
  await expect(page.getByRole('dialog')).toHaveCount(0)
  await expect(edit).toBeFocused()
})
