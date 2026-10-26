import { openTab } from './oneScreen.js'
import { choosePlaceForHome } from './pointSelection.js'
import { expect, test } from '@playwright/test'

// Controlled weather fixtures stay in browser memory. Existing historical/GIS endpoints use real local datasets;
// external network requests are blocked. Home shows the weather (the Weather page was merged into it); readings are
// stamped "now" because Home shows current conditions only while they are fresh.
const weather = point => ({ status: 'partial', message: 'Some values are unavailable.', location: point,
  current: { temperature_c: 27, humidity_percent: 70, precipitation_mm: 0, interval_seconds: 900, valid_at: new Date().toISOString(), stale: false },
  forecast: Array.from({ length: 7 }, (_, i) => ({ date: `2026-10-${String(8 + i).padStart(2, '0')}`, weather_code: i === 0 ? 0 : 61, precipitation_mm: i === 1 ? null : i, temperature_min_c: 20, temperature_max_c: 30 })),
  grid_location: { latitude: 13.35, longitude: 74.75 }, retrieved_at: new Date().toISOString(), prediction_status: 'not_available' })
const requested = url => url.searchParams.has('latitude') ? { latitude: Number(url.searchParams.get('latitude')), longitude: Number(url.searchParams.get('longitude')) } : null
const days = page => page.getByRole('list', { name: 'Daily weather forecasts' }).getByRole('article')
async function useMyLocation(page, context, latitude, longitude) {
  await context.grantPermissions(['geolocation']); await context.setGeolocation({ latitude, longitude, accuracy: 40 })
  await page.getByRole('button', { name: 'Use my location' }).click()
}

test.beforeEach(async ({ page }) => {
  await page.route('**/*', async route => {
    const url = new URL(route.request().url())
    if (!['127.0.0.1', 'localhost'].includes(url.hostname)) return route.abort()
    if (url.pathname === '/api/weather') return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(weather(requested(url))) })
    return route.continue()
  })
})

test('GPS and map selection on Home drive weather requests, and unavailable values remain honest', async ({ page, context }) => {
  const errors = []; page.on('pageerror', error => errors.push(error.message))
  await page.goto('/')
  await expect(page.getByRole('heading', { name: 'Karnataka statewide view' })).toBeVisible()
  const request = page.waitForRequest(r => r.url().includes('/api/weather?latitude=13.3419169&longitude=74.7473232'))
  await useMyLocation(page, context, 13.3419169, 74.7473232); await request
  await expect(page.getByRole('heading', { name: 'GPS-selected point', exact: true })).toBeVisible()
  await expect(page.getByText('27 °C', { exact: true })).toBeVisible()
  await expect(page.getByRole('list', { name: 'Daily weather forecasts' }).getByText('Unavailable', { exact: true })).toBeVisible()
  const map = page.getByRole('region', { name: 'Karnataka emergency map' })
  const clickedRequest = page.waitForRequest(r => r.url().includes('/api/weather?latitude=') && !r.url().includes('latitude=13.3419169'))
  await map.click({ position: { x: 260, y: 200 } })
  // A tap on open map offers "Check risk here"; on a rain-risk spot it offers "Full assessment here". Both choose that point.
  const plain = page.getByRole('button', { name: 'Check risk here' }), spot = page.getByRole('button', { name: 'Full assessment here' })
  await expect(plain.or(spot)).toBeVisible()
  await (await plain.isVisible() ? plain : spot).click(); await clickedRequest
  await expect(page.getByRole('heading', { name: 'GPS-selected point', exact: true })).toHaveCount(0)
  await expect(page.getByText('27 °C', { exact: true })).toBeVisible()
  await expect(days(page)).toHaveCount(7)
  await page.getByRole('navigation', { name: 'Main navigation' }).getByRole('link', { name: 'Flood Map' }).click()
  await expect(page.getByRole('heading', { name: 'Karnataka Flood Intelligence' })).toBeVisible()
  expect(errors).toEqual([])
})

test('mobile GPS permission denial leaves place choice open and shows an explicit weather failure', async ({ page, context }) => {
  await context.clearPermissions()
  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto('/')
  await expect(page.getByText(/Location permission was denied/)).toBeVisible()
  await page.route('**/api/weather?**', route => route.fulfill({ status: 503, contentType: 'application/json', body: JSON.stringify({ status: 'unavailable', message: 'Controlled provider outage' }) }))
  await choosePlaceForHome(page, 13.34, 74.74)
  await expect(page.getByText(/Controlled provider outage/)).toBeVisible()
  await expect(page.getByText('27 °C', { exact: true })).toHaveCount(0)
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
})

test('seven-day forecasts keep their order after GPS, another place and refresh on mobile, four days per page', async ({ page, context }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await context.grantPermissions(['geolocation'])
  await context.setGeolocation({ latitude: 13.34, longitude: 74.74, accuracy: 40 })
  const first = page.waitForRequest(r => r.url().includes('/api/weather?latitude=13.34&longitude=74.74'))
  await page.goto('/'); await first   // Home asks for the location once on the first visit
  const dates = Array.from({ length: 7 }, (_, i) => `2026-10-${String(8 + i).padStart(2, '0')}`)
  // Phones page the forecast instead of scrolling: four days, then the remaining three.
  async function allSevenInOrder() {
    await openTab(page, 'Weather'); const pager = page.getByRole('navigation', { name: 'More forecast days' })
    if (await pager.getByRole('button', { name: '‹ Previous' }).isEnabled()) await pager.getByRole('button', { name: '‹ Previous' }).click()
    await expect(days(page)).toHaveCount(4); const start = await days(page).locator('time').evaluateAll(n => n.map(x => x.dateTime))
    await pager.getByRole('button', { name: 'Next ›' }).click(); await expect(days(page)).toHaveCount(3)
    const rest = await days(page).locator('time').evaluateAll(n => n.map(x => x.dateTime))
    expect([...start, ...rest]).toEqual(dates)
  }
  await expect(page.getByRole('heading', { name: 'GPS-selected point', exact: true })).toBeVisible()
  await allSevenInOrder()
  const manual = page.waitForRequest(r => r.url().includes('/api/weather?latitude=14&longitude=75'))
  await choosePlaceForHome(page, 14, 75); await manual
  await allSevenInOrder()
  const refreshed = page.waitForRequest(r => r.url().includes('/api/weather?latitude=14&longitude=75'))
  await page.getByRole('button', { name: 'Refresh weather' }).click(); await refreshed
  await allSevenInOrder()
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
})

test('short and empty forecast coverage is explicit without invented dates, then failed refresh retains explicitly stale information', async ({ page, context }) => {
  await page.route('**/api/weather*', route => {
    const body = weather(requested(new URL(route.request().url()))); body.forecast = body.forecast.slice(0, 3)
    body.forecast_coverage = { valid_days: 3, missing_dates: ['2026-10-11', '2026-10-12', '2026-10-13', '2026-10-14'] }
    return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body) })
  })
  await page.goto('/'); await useMyLocation(page, context, 13.34, 74.74)
  await expect(page.getByRole('status', { name: '' }).filter({ hasText: 'Incomplete forecast coverage' })).toContainText('3 of 7')
  await expect(days(page)).toHaveCount(3)
  await expect(page.locator('.weather-strip time[datetime="2026-10-14"]')).toHaveCount(0)
  await page.route('**/api/weather*', route => {
    const body = weather(requested(new URL(route.request().url()))); body.forecast = []; body.forecast_coverage = { valid_days: 0, missing_dates: [] }
    return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body) })
  })
  await page.getByRole('button', { name: 'Refresh weather' }).click()
  await expect(page.getByText(/Daily forecast unavailable/)).toBeVisible()
  await expect(page.getByText('27 °C', { exact: true })).toBeVisible()
  await expect(page.getByRole('list', { name: 'Daily weather forecasts' })).toHaveCount(0)
  await page.route('**/api/weather*', route => route.fulfill({ status: 503, contentType: 'application/json', body: JSON.stringify({ status: 'unavailable', message: 'Controlled outage' }) }))
  await page.getByRole('button', { name: 'Refresh weather' }).click()
  await expect(page.getByText(/Controlled outage/)).toBeVisible()
  // Home never shows stale current conditions as current; the freshness line says what is shown.
  await expect(page.getByRole('heading', { name: 'Current weather unavailable' })).toBeVisible()
  await expect(page.getByRole('status', { name: 'Weather data freshness' })).toContainText('Stale — previously retrieved information')
})
