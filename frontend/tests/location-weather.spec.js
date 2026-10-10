import {selectPoint} from './pointSelection.js'
import { expect, test } from '@playwright/test'

// Controlled weather fixtures stay in browser memory. Existing historical/GIS
// endpoints use real local datasets; external network requests are blocked.
const weather = point => ({ status: 'partial', message: 'Some values are unavailable.', location: point,
  current: { temperature_c: 27, humidity_percent: 70, precipitation_mm: 0, interval_seconds: 900, valid_at: '2026-10-08T06:00:00+05:30', stale: false },
  forecast: Array.from({ length: 7 }, (_, i) => ({ date: `2026-10-${String(8 + i).padStart(2, '0')}`, weather_code: i === 0 ? 0 : 61, precipitation_mm: i === 1 ? null : i, temperature_min_c: 20, temperature_max_c: 30 })),
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
  await page.goto('/weather'); await page.getByText('Change location',{exact:true}).click()
  await expect(page.getByText('27 °C', { exact: true })).toBeVisible()

  const request = page.waitForRequest(r => r.url().includes('/api/weather?latitude=13.3419169&longitude=74.7473232'))
  await selectPoint(page,13.3419169,74.7473232); await request
  await expect(page.getByRole('heading', { name: 'GPS-selected point', exact: true })).toBeVisible()
  await expect(page.getByRole('list', { name: 'Daily weather forecasts' }).getByText('Unavailable', { exact: true })).toBeVisible()
  await expect(page.getByText(/Flood prediction is not available/)).toBeVisible()
  await page.getByRole('button', { name: 'Open weather map' }).click()
  const map = page.getByRole('region', { name: 'Weather location selection map' })
  await expect(map.locator('path.leaflet-interactive')).toHaveCount(1)
  const clickedRequest = page.waitForRequest(r => r.url().includes('/api/weather?latitude='))
  await map.click({ position: { x: 210, y: 190 } }); await clickedRequest
  await expect(page.getByRole('heading', { name: 'Selected map point', exact: true })).toBeVisible()
  await expect(page.getByText('27 °C', { exact: true })).toBeVisible()
  await expect(map.locator('path.leaflet-interactive')).toHaveCount(1)
  await page.getByRole('navigation', { name: 'Main navigation' }).getByRole('link', { name: 'Flood Map' }).click()
  await expect(page.getByRole('heading', { name: 'Karnataka Flood Intelligence' })).toBeVisible()
  expect(errors).toEqual([])
})

test('mobile GPS permission denial preserves manual point selection and explicit weather failure', async ({ page, context }) => {
  await context.clearPermissions()
  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto('/weather'); await page.getByText('Change location',{exact:true}).click()
  await page.getByRole('button', { name: 'Use my GPS location' }).click()
  await expect(page.getByText(/Location permission denied/)).toBeVisible()
  await page.route('**/api/weather?**', route => route.fulfill({ status: 503, contentType: 'application/json', body: JSON.stringify({ status: 'unavailable', message: 'Controlled provider outage' }) }))

  await selectPoint(page,13.34,74.74)
  await expect(page.getByText(/Controlled provider outage/)).toBeVisible()
  await expect(page.getByText('27 °C', { exact: true })).toHaveCount(0)
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
})

test('seven-day forecasts retain order after GPS, map, manual selection and refresh on mobile', async ({ page, context }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await context.grantPermissions(['geolocation'])
  await context.setGeolocation({ latitude: 13.34, longitude: 74.74, accuracy: 40 })
  await page.goto('/weather'); await page.getByText('Change location',{exact:true}).click()
  const cards = page.getByRole('list', { name: 'Daily weather forecasts' }).getByRole('article')
  await expect(cards).toHaveCount(7)
  expect(await cards.locator('time').evaluateAll(nodes => nodes.map(n => n.dateTime))).toEqual(Array.from({ length: 7 }, (_, i) => `2026-10-${String(8 + i).padStart(2, '0')}`))
  const gps = page.waitForRequest(r => r.url().includes('/api/weather?latitude=13.34&longitude=74.74'))
  await page.getByRole('button', { name: 'Use my GPS location' }).click(); await gps
  await expect(page.getByRole('heading', { name: 'GPS-selected point', exact: true })).toBeVisible()
  await expect(cards).toHaveCount(7)
  await page.getByRole('button', { name: 'Open weather map' }).click()
  const clicked = page.waitForRequest(r => r.url().includes('/api/weather?latitude='))
  await page.getByRole('region', { name: 'Weather location selection map' }).click({ position: { x: 100, y: 150 } }); await clicked
  await expect(page.getByRole('heading', { name: 'Selected map point', exact: true })).toBeVisible()
  await expect(cards).toHaveCount(7)

  const manual = page.waitForRequest(r => r.url().includes('/api/weather?latitude=14&longitude=75'))
  await selectPoint(page,14,75); await manual
  await expect(cards).toHaveCount(7)
  const refreshed = page.waitForRequest(r => r.url().includes('/api/weather?latitude=14&longitude=75'))
  await page.getByRole('button', { name: 'Refresh weather' }).click(); await refreshed
  await expect(cards).toHaveCount(7)
  await expect(page.getByText(/Flood prediction is not available/)).toBeVisible()
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
})

test('short and empty forecast coverage is explicit without invented dates, then failed refresh retains explicitly stale information', async ({ page }) => {
  await page.route('**/api/weather*', route => {
    const body = weather(null); body.forecast = body.forecast.slice(0, 3)
    body.forecast_coverage = { valid_days: 3, missing_dates: ['2026-10-11', '2026-10-12', '2026-10-13', '2026-10-14'] }
    return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body) })
  })
  await page.goto('/weather'); await page.getByText('Change location',{exact:true}).click()
  await expect(page.getByRole('status', { name: '' }).filter({ hasText: 'Incomplete forecast coverage' })).toContainText('3 of 7')
  await expect(page.getByRole('list', { name: 'Daily weather forecasts' }).getByRole('article')).toHaveCount(3)
  await expect(page.locator('.daily-forecast time[datetime="2026-10-14"]')).toHaveCount(0)
  await page.route('**/api/weather*', route => {
    const body = weather(null); body.forecast = []; body.forecast_coverage = { valid_days: 0, missing_dates: [] }
    return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body) })
  })
  await page.getByRole('button', { name: 'Refresh weather' }).click()
  await expect(page.getByText(/Daily forecast unavailable/)).toBeVisible()
  await expect(page.getByText('27 °C', { exact: true })).toBeVisible()
  await expect(page.getByRole('list', { name: 'Daily weather forecasts' })).toHaveCount(0)
  await page.route('**/api/weather*', route => route.fulfill({ status: 503, contentType: 'application/json', body: JSON.stringify({ status: 'unavailable', message: 'Controlled outage' }) }))
  await page.getByRole('button', { name: 'Refresh weather' }).click()
  await expect(page.getByText(/Controlled outage/)).toBeVisible()
  await expect(page.getByText('27 °C', { exact: true })).toHaveCount(1)
  await expect(page.getByRole('status', { name: 'Weather data freshness' })).toContainText('Stale — previously retrieved information')
})
