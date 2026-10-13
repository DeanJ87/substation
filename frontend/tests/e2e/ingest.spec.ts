// T105: sign in, watch a dataset update as a sub lands, then fix a sub with no FILTER via Reconcile.
// Needs a running stack whose capture library is SUBSTATION_E2E_CAPTURE on this machine, and a real NINA
// XISF sub to copy (SUBSTATION_E2E_SOURCE, only ever read). Each run writes uniquely altered copies, so the
// content is always new to SubStation.
import { expect, test } from '@playwright/test'
import { existsSync, readFileSync, renameSync, writeFileSync } from 'node:fs'
import { join } from 'node:path'
import { signIn } from './helpers'

const CAPTURE = process.env.SUBSTATION_E2E_CAPTURE ?? ''
const SOURCE = process.env.SUBSTATION_E2E_SOURCE ?? ''
const DATASET = 'NGC 7000 · Panel 1 · OIII'

test.skip(!existsSync(SOURCE) || !existsSync(CAPTURE), 'set SUBSTATION_E2E_CAPTURE and SUBSTATION_E2E_SOURCE')

/** Copy an XISF with some header elements blanked (same length, so attachments stay valid) and a unique
 * marker written into the first blank, so the content is new every run. */
function alteredCopy(remove: RegExp[], name: string): string {
  const buf = Buffer.from(readFileSync(SOURCE))
  const len = buf.readUInt32LE(8)
  let xml = buf.subarray(16, 16 + len).toString('latin1')
  const marker = `<!--e2e ${Date.now()} ${Math.random().toString(36).slice(2, 8)}-->`
  let placed = false
  for (const rx of remove) {
    xml = xml.replace(rx, (m) => {
      if (!placed && m.length >= marker.length) {
        placed = true
        return marker + ' '.repeat(m.length - marker.length)
      }
      return ' '.repeat(m.length)
    })
  }
  if (!placed) throw new Error('nowhere to put the marker')
  buf.write(xml, 16, 'latin1')
  const dst = join(CAPTURE, 'e2e', name)
  const tmp = join(CAPTURE, 'e2e', `.${name}.part`)
  writeFileSync(tmp, buf, { flag: 'w' })
  renameSync(tmp, dst) // appears complete, as NINA's final rename does
  return dst
}

function subCount(text: string): number {
  const m = text.match(/(\d+) subs/)
  return m ? Number(m[1]) : -1
}

test('a new sub appears in its dataset, and a sub without FILTER is fixed in Reconcile', async ({ page }) => {
  const { mkdirSync } = await import('node:fs')
  mkdirSync(join(CAPTURE, 'e2e'), { recursive: true })
  await signIn(page)

  await page.getByRole('link').filter({ hasText: 'NGC 7000' }).filter({ hasText: 'Panel 1' }).first().click()
  await expect(page.getByRole('heading', { name: DATASET })).toBeVisible()
  const subtitle = page.locator('header div').filter({ hasText: /subs/ }).first()
  const before = subCount(await subtitle.innerText())
  expect(before).toBeGreaterThan(0)

  // 1. A complete sub lands (USBLIMIT blanked to make the content new): the dataset grows, live
  const stamp = Date.now()
  alteredCopy(
    [/<FITSKeyword name="USBLIMIT"[^>]*\/>/],
    `2026-10-07_20-27-58_OIII_-20.00_600.00s_e2e${stamp}.xisf`,
  )
  await expect.poll(async () => subCount(await subtitle.innerText()), { timeout: 110_000 }).toBe(before + 1)

  // 2. A sub without FILTER lands: it waits in Reconcile until a value is given
  alteredCopy(
    [
      /<FITSKeyword name="FILTER"[^>]*\/>/,
      /<Property id="Instrument:Filter:Name"[^>]*?(\/>|>.*?<\/Property>)/s,
    ],
    `nofilter_e2e${stamp}.xisf`,
  )
  await page.getByRole('link', { name: /Reconcile/ }).click()
  const group = page.locator('li').filter({ hasText: 'Filter missing' }).filter({ hasText: 'capture/e2e/' })
  await expect(group).toBeVisible({ timeout: 110_000 })
  await group.getByRole('textbox', { name: 'Filter' }).fill('OIII')
  await group.getByRole('button', { name: /^Set for/ }).click()
  await expect(group).toHaveCount(0)

  await page.getByRole('link', { name: 'Datasets' }).click()
  await page.getByRole('link').filter({ hasText: 'NGC 7000' }).filter({ hasText: 'Panel 1' }).first().click()
  await expect.poll(async () => subCount(await subtitle.innerText()), { timeout: 30_000 }).toBe(before + 2)
})
