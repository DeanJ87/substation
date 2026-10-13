// T106: axe on every screen in dark, light and night vision.
import { AxeBuilder } from '@axe-core/playwright'
import { expect, test } from '@playwright/test'
import { signIn } from './helpers'

const THEMES = ['dark', 'light', 'night'] as const
const SCREENS = ['/', '/reconcile', '/calibration', '/settings', '/queue']

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
      const r = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21aa']).analyze()
      for (const v of r.violations)
        failures.push(`${path}: ${v.id} (${v.nodes.length}) ${v.nodes[0]?.target.join(' ')} — ${v.help}`)
      if (path.startsWith('/datasets/')) {
        await page.locator('tbody tr').first().click()
        await page.getByRole('dialog').waitFor()
        const d = await new AxeBuilder({ page })
          .include('[role=dialog]')
          .withTags(['wcag2a', 'wcag2aa'])
          .analyze()
        for (const v of d.violations)
          failures.push(`${path} sub: ${v.id} ${v.nodes[0]?.target.join(' ')} — ${v.help}`)
      }
    }
    expect(failures).toEqual([])
  })
}
