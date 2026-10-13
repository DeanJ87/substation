import { expect, type Page } from '@playwright/test'

export const USER = process.env.SUBSTATION_E2E_USER ?? 'admin'
export const PASSWORD = process.env.SUBSTATION_E2E_PASSWORD ?? 'change-me-please'

export async function signIn(page: Page) {
  await page.goto('/sign-in')
  await page.getByLabel(/username/i).fill(USER)
  await page.getByLabel(/password/i).fill(PASSWORD)
  await page.getByRole('button', { name: /sign in/i }).click()
  await expect(page.getByRole('navigation', { name: 'Main' })).toBeVisible()
}
