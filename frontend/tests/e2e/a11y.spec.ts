// T106, 007-DR-27: axe (WCAG 2.2 A and AA) on every screen in dark, light and night vision, and on the sub viewer.
import { AxeBuilder } from '@axe-core/playwright'
import { expect, test } from '@playwright/test'
import { signIn } from './helpers'

const THEMES = ['dark', 'light', 'night'] as const
const SCREENS = ['/', '/reconcile', '/calibration', '/settings', '/activity', '/map', '/bin']
const TAGS = ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa']

for (const theme of THEMES) {
  test(`no accessibility violations in ${theme}`, async ({ page }) => {
    await page.addInitScript((t) => localStorage.setItem('sst-theme', t), theme)
    await signIn(page)
    const pages = [...SCREENS]
    // and one dataset, one night and one open sub
    await page.goto('/')
    const first = page.locator('a[href^="/datasets/"]').first()
    if (await first.count()) pages.push((await first.getAttribute('href'))!)
    const failures: string[] = []
    for (const path of pages) {
      await page.goto(path)
      await page.waitForLoadState('networkidle')
      // map tiles are pictures drawn by OpenStreetMap, outside SubStation's control
      const r = await new AxeBuilder({ page }).withTags(TAGS).exclude('.leaflet-tile-pane').analyze()
      for (const v of r.violations)
        failures.push(`${path}: ${v.id} (${v.nodes.length}) ${v.nodes[0]?.target.join(' ')} — ${v.help}`)
      if (path.startsWith('/datasets/')) {
        // the sub viewer opens as a modal over the grid (spec 012)
        await page
          .getByRole('button', { name: /^Select / })
          .first()
          .dblclick()
        await page.getByRole('dialog').waitFor()
        await page.waitForLoadState('networkidle')
        const d = await new AxeBuilder({ page }).include('[role=dialog]').withTags(TAGS).analyze()
        for (const v of d.violations)
          failures.push(`${path} sub: ${v.id} ${v.nodes[0]?.target.join(' ')} — ${v.help}`)
      }
    }
    expect(failures).toEqual([])
  })
}
