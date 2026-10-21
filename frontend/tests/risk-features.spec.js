import { test, expect } from '@playwright/test'
import { mkdir } from 'node:fs/promises'

// Live checks: the backend calls real Open-Meteo/GloFAS/elevation APIs. The shelter
// route UI test uses a conspicuously labelled fixture shelter and fixture route.
const evidence = process.env.FLOODPULSE_EVIDENCE_DIR || '/tmp/floodpulse-v2-verification'
const LEVELS = ['Low', 'Moderate', 'High', 'Severe', 'Unavailable']
const nav = page => page.getByRole('navigation', { name: 'Main navigation' })

test.beforeAll(async () => { await mkdir(evidence, { recursive: true }) })

async function chooseKundapur(page) {
  await page.route('**api.bigdatacloud.net/**', r => r.abort())
  await page.goto('/'); await page.setViewportSize({ width: 1366, height: 768 })
  await page.getByRole('button', { name: 'Search districts and localities' }).click()
  await page.getByLabel('Karnataka district', { exact: true }).selectOption('nic:udupi.nic.in')
  await page.getByRole('button', { name: /^Kundapur — Udupi/ }).click()
}

test('live point risk on Home and the statewide risk grid on Flood Map', async ({ page }) => {
  test.setTimeout(120000)
  const riskResponse = page.waitForResponse(r => r.url().includes('/api/risk?latitude=13.62510'), { timeout: 60000 })
  await chooseKundapur(page)
  const risk = await riskResponse
  const body = await risk.json()
  expect(risk.status()).toBe(200)
  expect(body.experimental).toBe(true); expect(body.official_warning).toBe(false)
  expect(['low', 'moderate', 'high', 'severe']).toContain(body.flood.level)
  const card = page.locator('.risk-why button')
  await expect(card).toContainText('Flood'); await expect(card).toContainText('Drainage')
  await expect(page.locator('.imd-card')).toBeVisible(); await expect(page.locator('.sachet-card')).toBeVisible()
  const badgeText = await card.locator('.risk-badge').first().textContent()
  expect(LEVELS).toContain(badgeText)
  await card.click()
  await expect(page.getByRole('dialog', { name: 'Why this risk level? (experimental)' })).toBeVisible()
  await expect(page.getByRole('rowheader', { name: /Forecast rain, next 24 h/ }).first()).toBeVisible()
  await page.getByRole('dialog').getByRole('tab', { name: 'About' }).click()
  await expect(page.locator('.risk-why-body').getByText(/Experimental risk index — rule-based/)).toBeVisible()
  const size = await page.evaluate(() => ({ h: document.documentElement.scrollHeight, w: document.documentElement.scrollWidth }))
  expect(size).toEqual({ h: 768, w: 1366 })
  await page.screenshot({ path: evidence + '/01-home-risk.png' })
  await page.getByRole('button', { name: 'Close', exact: true }).click()

  const gridResponse = page.waitForResponse(r => r.url().endsWith('/api/risk/grid'), { timeout: 90000 })
  await nav(page).getByRole('link', { name: 'Flood Map', exact: true }).click()
  const grid = await gridResponse
  const gridBody = await grid.json()
  expect(grid.status()).toBe(200); expect(gridBody.cells).toHaveLength(256)
  await expect(page.getByRole('checkbox', { name: 'Rain risk, next 24 h' })).toBeChecked()
  await page.getByRole('tab', { name: 'Today', exact: true }).click()
  await expect(page.getByText(/(of 256 areas High or Severe|all 256 areas Low or unavailable)/)).toBeVisible()
  await expect(page.getByLabel('Rain risk legend')).toBeVisible()
  expect(await page.locator('.intelligence-map path.leaflet-interactive').count()).toBeGreaterThanOrEqual(256)
  await page.screenshot({ path: evidence + '/02-flood-map-risk-grid.png' })
})

test('administrator sees draft-only alert suggestions from the risk engine', async ({ page }) => {
  test.skip(!process.env.FLOODPULSE_REPORT_TEST_PASSWORD, 'Requires disposable database runner')
  test.setTimeout(120000)
  await page.goto('/admin')
  await page.getByLabel('Username', { exact: true }).fill('test-report-admin')
  await page.getByLabel('Password', { exact: true }).fill(process.env.FLOODPULSE_REPORT_TEST_PASSWORD)
  await page.getByRole('button', { name: 'Sign in', exact: true }).click()
  const suggestions = page.waitForResponse(r => r.url().endsWith('/api/admin/risk/suggestions'), { timeout: 90000 })
  await page.getByRole('button', { name: 'Telegram notifications' }).click()
  const response = await suggestions
  expect(response.status()).toBe(200)
  const body = await response.json()
  expect(body.note).toContain('explicitly approve')
  await expect(page.getByRole('heading', { name: 'Suggested alerts from the risk engine' })).toBeVisible()
  await expect(page.getByText('Drafts only. Nothing is sent until you edit, preview and approve it.')).toBeVisible()
  if (body.suggestions.length) await expect(page.getByRole('button', { name: 'Use as draft' }).first()).toBeVisible()
  else await expect(page.getByText('No grid cell is currently High or Severe. No alert is suggested.')).toBeVisible()
  await page.screenshot({ path: evidence + '/03-admin-risk-suggestions.png', fullPage: true })
  // Unauthenticated access is refused.
  const anonymous = await page.context().browser().newContext()
  const denied = await anonymous.request.get(new URL('/api/admin/risk/suggestions', page.url()).href)
  expect(denied.status()).toBe(401)
  await anonymous.close()
})

test('routing without a key is honestly not configured; route UI draws a labelled fixture route', async ({ page }) => {
  test.setTimeout(90000)
  const real = await page.request.post('/api/route', { data: { shelter_id: '11111111-1111-1111-1111-111111111111', origin: { latitude: 13.62, longitude: 74.69, accuracy_m: 50 } } })
  expect(real.status()).toBe(503)
  expect((await real.json()).status).toBe('not_configured')

  const now = Date.now()
  const fixture = { id: '11111111-1111-1111-1111-111111111111', name: 'FIXTURE — not a real shelter', address: 'Test only', district_id: 'nic:udupi.nic.in',
    district_name: 'Udupi', latitude: 13.35, longitude: 74.79, capacity: 50, occupancy: 10, available_capacity: 40, water: 'yes', toilets: 'yes',
    accessibility: 'yes', status: 'open', verified_at: new Date(now - 3600000).toISOString(), updated_at: new Date(now - 3600000).toISOString(),
    verification_expires_at: new Date(now + 3600000).toISOString(), restrictions: null, demonstration: true, contact: null, straight_line_km: 31.1,
    directions_url: 'https://www.google.com/maps/dir/?api=1&destination=13.35,74.79' }
  await page.route('**/api/shelters*', r => r.fulfill({ json: { status: 'available', mode: 'demonstration', shelters: [fixture], total: 1, retrieved_at: new Date().toISOString(), verification_valid_hours: 24 } }))
  await page.route('**/api/route', r => r.fulfill({ json: { status: 'available', provider: 'openrouteservice', profile: 'foot-walking',
    geometry: { type: 'LineString', coordinates: [[74.6916, 13.6251], [74.72, 13.5], [74.79, 13.35]] }, distance_m: 32100, duration_s: 23100,
    steps: [{ instruction: 'FIXTURE step', distance_m: 100, duration_s: 60 }], avoided_reports: 1, flood_safe_certified: false,
    label: 'Route avoids 1 approved flooding/blocked-drain report area(s) from the last 72 hours. It is NOT certified flood-safe: check road closures and follow local authorities.',
    shelter: { id: fixture.id, name: fixture.name }, attribution: '© openrouteservice.org by HeiGIT | Map data © OpenStreetMap contributors' } }))
  await chooseKundapur(page)
  await nav(page).getByRole('link', { name: 'Shelters', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'FIXTURE — not a real shelter' })).toBeVisible()
  await page.getByRole('button', { name: 'Show walking route on map' }).click()
  await expect(page.getByText(/NOT certified flood-safe/)).toBeVisible()
  await expect(page.getByText('32.1 km · about 385 min walking')).toBeVisible()
  await expect(page.locator('.shelter-map path[stroke="#1565c0"]')).toHaveCount(1)
  await page.screenshot({ path: evidence + '/04-shelter-route-fixture.png' })
})
