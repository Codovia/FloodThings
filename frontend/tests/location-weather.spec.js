import { expect, test } from '@playwright/test'

// Controlled weather fixtures stay in browser memory. Existing historical/GIS
// endpoints use real local datasets; external network requests are blocked.
const weather = point => ({ status: 'partial', message: 'Some values are unavailable.', location: point,
  current: { temperature_c: 27, humidity_percent: 70, precipitation_mm: 0, interval_seconds: 900, valid_at: '2026-10-08T06:00:00+05:30', stale: false },
  forecast: [{ date: '2026-10-08', precipitation_mm: 1, temperature_min_c: 20, temperature_max_c: 30 },
    { date: '2026-10-09', precipitation_mm: null, temperature_min_c: 21, temperature_max_c: 31 },
    { date: '2026-10-10', precipitation_mm: 3, temperature_min_c: 21, temperature_max_c: 30 }],
  grid_location: { latitude: 13.35, longitude: 74.75 }, retrieved_at: '2026-10-08T00:31:00Z', prediction_status: 'not_available' })

test.beforeEach(async ({ page }) => {
  await page.route('**/*', async route => {
    const url = new URL(route.request().url())
    if (!['127.0.0.1', 'localhost'].includes(url.hostname)) return route.abort()
    if (url.pathname === '/api/weather') {
      const point = url.searchParams.has('latitude') ? { latitude: Number(url.searchParams.get('latitude')), longitude: Number(url.searchParams.get('longitude')) } : null
      return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(weather(point)) })
    }
    return route.continue()
  })
})

test('coordinate and Leaflet selection drive weather requests, and source masks/unavailable values remain honest', async ({ page }) => {
  const errors = []; page.on('pageerror', error => errors.push(error.message))
  await page.goto('/')
  await expect(page.getByText('27 °C', { exact: true })).toBeVisible()
  await page.getByLabel('Weather latitude').fill('13.3419169')
  await page.getByLabel('Weather longitude').fill('74.7473232')
  const request = page.waitForRequest(r => r.url().includes('/api/weather?latitude=13.3419169&longitude=74.7473232'))
  await page.getByRole('button', { name: 'Get point weather' }).click(); await request
  await expect(page.getByRole('heading', { name: 'Entered coordinates', exact: true })).toBeVisible()
  await expect(page.getByText('Unavailable', { exact: true })).toBeVisible()
  await expect(page.getByText(/Flood prediction is not available/)).toBeVisible()
  await page.getByRole('button', { name: 'Open weather map' }).click()
  const map = page.getByRole('region', { name: 'Weather location selection map' })
  await expect(map.locator('path.leaflet-interactive')).toHaveCount(1)
  const clickedRequest = page.waitForRequest(r => r.url().includes('/api/weather?latitude='))
  await map.click({ position: { x: 210, y: 190 } }); await clickedRequest
  await expect(page.getByRole('heading', { name: 'Selected map point', exact: true })).toBeVisible()
  await expect(page.getByText('27 °C', { exact: true })).toBeVisible()
  await expect(map.locator('path.leaflet-interactive')).toHaveCount(1)
  await expect(page.getByRole('heading', { name: 'Udupi flood event maps' })).toBeVisible()
  expect(errors).toEqual([])
})

test('mobile GPS permission denial preserves manual point selection and explicit weather failure', async ({ page, context }) => {
  await context.clearPermissions()
  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto('/')
  await page.getByRole('button', { name: 'Use my GPS location' }).click()
  await expect(page.getByText(/Location permission denied/)).toBeVisible()
  await page.route('**/api/weather?**', route => route.fulfill({ status: 503, contentType: 'application/json', body: JSON.stringify({ status: 'unavailable', message: 'Controlled provider outage' }) }))
  await page.getByLabel('Weather latitude').fill('13.34'); await page.getByLabel('Weather longitude').fill('74.74')
  await page.getByRole('button', { name: 'Get point weather' }).click()
  await expect(page.getByText(/Controlled provider outage/)).toBeVisible()
  await expect(page.getByText('27 °C', { exact: true })).toHaveCount(0)
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
})
