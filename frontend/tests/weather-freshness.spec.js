import { expect, test } from '@playwright/test'

// Browser-only fixtures and deterministic clocks; no provider calls or files.
const START = new Date('2026-10-08T06:00:00Z')
const SIX_HOURS = 6 * 60 * 60 * 1000
const payload = (point, retrieved) => ({ status: 'available', location: point, retrieved_at: retrieved,
  current: { temperature_c: 27, humidity_percent: 70, precipitation_mm: 0, interval_seconds: 900, valid_at: '2026-10-08T11:30:00+05:30', stale: false },
  forecast: Array.from({ length: 7 }, (_, i) => ({ date: `2026-10-${String(8 + i).padStart(2, '0')}`, weather_code: 61, precipitation_mm: i, temperature_min_c: 20, temperature_max_c: 30 })),
  forecast_coverage: { valid_days: 7, missing_dates: [], start_date: '2026-10-08' },
  grid_location: { latitude: 13.35, longitude: 74.75 }, forecast_issued_at: null,
})
async function setup(page) {
  const state = { requests: [], fail: false, hold: null, waiting: null, timestampMissing: false }
  await page.clock.install({ time: START })
  await page.clock.pauseAt(START)
  await page.route('**/*', async route => {
    const url = new URL(route.request().url())
    if (!['127.0.0.1', 'localhost'].includes(url.hostname)) return route.abort()
    if (url.pathname !== '/api/weather') return route.continue()
    state.requests.push(url.pathname + url.search)
    const point = url.searchParams.has('latitude') ? { latitude: +url.searchParams.get('latitude'), longitude: +url.searchParams.get('longitude') } : { latitude: 12.9767936, longitude: 77.590082 }
    const timestamp = await page.evaluate(() => new Date().toISOString())
    if (state.hold) { state.waiting = route; await state.hold }
    if (state.fail) return route.fulfill({ status: 503, contentType: 'application/json', body: JSON.stringify({ status: 'unavailable', message: 'Controlled provider outage' }) })
    return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(payload(point, state.timestampMissing ? null : timestamp)) })
  })
  await page.goto('/')
  return state
}
const freshness = page => page.getByRole('status', { name: 'Weather data freshness' })
async function activate(page, hidden) {
  await page.evaluate(value => {
    Object.defineProperty(document, 'hidden', { configurable: true, get: () => value })
    document.dispatchEvent(new Event('visibilitychange'))
    if (!value) { window.dispatchEvent(new Event('focus')); window.dispatchEvent(new Event('online')) }
  }, hidden)
}

test('fresh before six hours, automatically refreshes when due, manual refresh works and seven dates stay ordered', async ({ page }) => {
  const state = await setup(page)
  await expect(freshness(page)).toHaveAttribute('data-freshness', 'fresh')
  expect(state.requests).toEqual(['/api/weather'])
  await page.clock.fastForward(SIX_HOURS - 1)
  await activate(page, false)
  expect(state.requests).toHaveLength(1)
  let release; state.hold = new Promise(resolve => { release = resolve })
  await page.clock.fastForward(1)
  await expect(freshness(page)).toHaveAttribute('data-freshness', 'refreshing')
  await activate(page, false); await activate(page, false)
  expect(state.requests).toHaveLength(2)
  await expect(page.getByText('27 °C', { exact: true })).toBeVisible()
  await expect(freshness(page)).toContainText('Showing previously retrieved information')
  await expect(freshness(page)).toContainText('Displayed information is stale')
  release(); state.hold = null
  await expect(freshness(page)).toHaveAttribute('data-freshness', 'fresh')
  await page.getByRole('button', { name: 'Refresh weather' }).click()
  await expect.poll(() => state.requests.length).toBe(3)
  await expect(freshness(page)).toHaveAttribute('data-freshness', 'fresh')
  const cards = page.getByRole('list', { name: 'Daily weather forecasts' }).getByRole('article')
  await expect(cards).toHaveCount(7)
  expect(await cards.locator('time').evaluateAll(nodes => nodes.map(n => n.dateTime))).toEqual(Array.from({ length: 7 }, (_, i) => `2026-10-${String(8 + i).padStart(2, '0')}`))
  await expect(page.getByText('Latitude 13.35°, longitude 74.75°')).toBeVisible()
  await expect(page.getByText('Unavailable — provider does not supply it here')).toBeVisible()
  await expect(page.getByText(/Flood prediction is not available/)).toBeVisible()
})

test('hidden tab reactivation checks stale age, errors retain explicitly stale weather and retries stop after three attempts', async ({ page }) => {
  const state = await setup(page)
  await expect(freshness(page)).toHaveAttribute('data-freshness', 'fresh')
  await activate(page, true)
  await page.clock.fastForward(SIX_HOURS)
  expect(state.requests).toHaveLength(1)
  state.fail = true
  await activate(page, false)
  await expect(freshness(page)).toHaveAttribute('data-freshness', 'stale')
  await expect(page.getByRole('alert')).toContainText('Controlled provider outage')
  await expect(page.getByText('27 °C', { exact: true })).toBeVisible()
  await activate(page, false); await activate(page, false)
  expect(state.requests).toHaveLength(2)
  await page.clock.fastForward(30 * 60 * 1000)
  await expect.poll(() => state.requests.length).toBe(3)
  await expect(freshness(page)).toHaveAttribute('data-freshness', 'stale')
  await page.clock.fastForward(60 * 60 * 1000)
  await expect.poll(() => state.requests.length).toBe(4)
  await expect(freshness(page)).toContainText('Automatic retries paused after three failed attempts')
  await page.clock.fastForward(SIX_HOURS)
  await activate(page, false); expect(state.requests).toHaveLength(4)
  state.fail = false
  await page.getByRole('button', { name: 'Refresh weather' }).click()
  await expect(freshness(page)).toHaveAttribute('data-freshness', 'fresh')
  expect(state.requests).toHaveLength(5)
})

test('offline expiry becomes stale, reconnect refreshes selected Udupi and mobile layout remains usable', async ({ page, context }) => {
  const state = await setup(page)
  await expect(freshness(page)).toHaveAttribute('data-freshness', 'fresh')
  await page.setViewportSize({ width: 390, height: 844 })
  await page.getByLabel('Weather latitude').fill('13.34'); await page.getByLabel('Weather longitude').fill('74.74')
  await page.getByRole('button', { name: 'Get point weather' }).click()
  await expect(freshness(page)).toHaveAttribute('data-freshness', 'fresh')
  await expect(page.getByRole('heading', { name: 'Entered coordinates', exact: true })).toBeVisible()
  await expect.poll(() => state.requests.length).toBe(2)
  await context.setOffline(true)
  await page.clock.fastForward(SIX_HOURS)
  await expect(freshness(page)).toHaveAttribute('data-freshness', 'stale')
  await expect(freshness(page)).toContainText('Browser is offline')
  expect(state.requests).toHaveLength(2)
  await context.setOffline(false)
  await expect.poll(() => state.requests.length).toBe(3)
  await expect(freshness(page)).toHaveAttribute('data-freshness', 'fresh')
  expect(state.requests.at(-1)).toBe('/api/weather?latitude=13.34&longitude=74.74')
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  await page.screenshot({ path: '/tmp/sprint3-fresh-mobile.png', fullPage: true })
})

test('missing retrieval time is explicitly unverified, does not fabricate freshness or request repeatedly', async ({ page }) => {
  const state = await setup(page)
  await expect(freshness(page)).toHaveAttribute('data-freshness', 'fresh')
  state.timestampMissing = true
  await page.getByRole('button', { name: 'Refresh weather' }).click()
  await expect(freshness(page)).toHaveAttribute('data-freshness', 'stale')
  await expect(freshness(page)).toContainText('Unavailable — freshness cannot be verified')
  await activate(page, false); await activate(page, false)
  expect(state.requests).toHaveLength(2)
  await expect(page.getByRole('list', { name: 'Daily weather forecasts' }).getByRole('article')).toHaveCount(7)
})

test('switching location during an automatic refresh never renders the old location result', async ({ page }) => {
  const state = await setup(page)
  await expect(freshness(page)).toHaveAttribute('data-freshness', 'fresh')
  let release; state.hold = new Promise(resolve => { release = resolve })
  await page.clock.fastForward(SIX_HOURS)
  await expect(freshness(page)).toHaveAttribute('data-freshness', 'refreshing')
  await expect.poll(() => state.requests.length).toBe(2)
  state.hold = null
  await page.getByLabel('Weather latitude').fill('13.34'); await page.getByLabel('Weather longitude').fill('74.74')
  await page.getByRole('button', { name: 'Get point weather' }).click()
  await expect(freshness(page)).toHaveAttribute('data-freshness', 'fresh')
  await expect(page.getByText(/Requested point: 13.34° latitude, 74.74° longitude/)).toBeVisible()
  release()
  await page.evaluate(() => new Promise(resolve => queueMicrotask(resolve)))
  await expect(page.getByRole('heading', { name: 'Entered coordinates', exact: true })).toBeVisible()
  await page.getByRole('button', { name: 'Refresh weather' }).click()
  await expect.poll(() => state.requests.length).toBe(4)
  expect(state.requests.slice(-2)).toEqual(['/api/weather?latitude=13.34&longitude=74.74', '/api/weather?latitude=13.34&longitude=74.74'])
  await expect(freshness(page)).toHaveAttribute('data-freshness', 'fresh')
  await expect(page.getByRole('list', { name: 'Daily weather forecasts' }).getByRole('article')).toHaveCount(7)
})
