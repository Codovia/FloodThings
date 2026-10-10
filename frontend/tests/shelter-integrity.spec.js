import { expect, test } from '@playwright/test'

const record = () => ({ id: 'isolated-fixture', name: 'DEMONSTRATION ONLY — not a shelter', address: 'Isolated fixture', district_name: 'Udupi', latitude: 13.5, longitude: 74.7, capacity: 10, occupancy: 2, available_capacity: 8, water: 'yes', toilets: 'unknown', accessibility: 'TEST ONLY', status: 'open', verified_at: new Date().toISOString(), updated_at: new Date().toISOString(), verification_expires_at: new Date(Date.now() + 86400000).toISOString(), demonstration: true, straight_line_km: null })
const directory = rows => ({ status: 'available', mode: 'demonstration', total: rows.length, verification_valid_hours: 24, shelters: rows })
test.beforeEach(async ({ page }) => {
  await page.route('**/*', route => ['localhost', '127.0.0.1'].includes(new URL(route.request().url()).hostname) ? route.continue() : route.abort())
})
test('active shelter page removes an assignment after the one-minute check', async ({ page }) => {
  await page.clock.install({ time: new Date() })
  let calls = 0
  await page.route('**/api/shelters*', route => route.fulfill({ json: directory(++calls === 1 ? [record()] : []) }))
  await page.goto('/shelters')
  await expect(page.getByText('DEMONSTRATION ONLY — not a shelter', { exact: true })).toBeVisible()
  await page.clock.runFor(60000)
  await expect(page.getByText('No currently verified open shelters are available in this directory.')).toBeVisible()
  expect(calls).toBe(2)
  await expect(page.getByRole('link', { name: /directions/ })).toHaveCount(0)
})
test('directions are disclosed only after a fresh check and a failure removes destinations', async ({ page }) => {
  let fail = false
  await page.route('**/api/shelters*', route => route.fulfill(fail ? { status: 503, json: { detail: 'Controlled directory outage' } } : { json: directory([record()]) }))
  await page.goto('/shelters')
  const link = page.getByRole('link', { name: 'Inspect demonstration directions (not for travel)' })
  await expect(link).toHaveCount(0)
  await page.getByRole('button', { name: 'Recheck availability for directions' }).click()
  await expect(link).toBeVisible()
  expect(new URL(await link.getAttribute('href')).searchParams.get('destination')).toBe('13.5,74.7')
  fail = true
  await page.getByRole('button', { name: 'Refresh shelters' }).click()
  await expect(page.getByText(/Controlled directory outage/)).toBeVisible()
  await expect(link).toHaveCount(0)
})
