import { expect, test } from '@playwright/test'
import { readFileSync } from 'node:fs'
import { tmpdir } from 'node:os'

const dataset = new URL('../../data/processed/udupi_flood_spatial_v1/', import.meta.url)
const saved = (id) => JSON.parse(readFileSync(new URL(`event_${id}.geojson`, dataset), 'utf8'))

test.beforeEach(async ({ page }) => {
  // Browser tests permit local application requests only. Weather fixtures never reach research files.
  await page.route('**/*', async route => {
    const url = new URL(route.request().url())
    if (!['127.0.0.1', 'localhost'].includes(url.hostname)) return route.abort()
    if (url.pathname === '/api/weather') return route.fulfill({ status: 503, contentType: 'application/json', body: JSON.stringify({ status: 'unavailable', message: 'Weather intentionally isolated in map test' }) })
    return route.continue()
  })
})

test('both event geometries match exported coordinates and Leaflet draws every retained cell', async ({ page }) => {
  const errors = []
  page.on('pageerror', error => errors.push(error.message))
  await page.goto('/')
  await expect(page.getByText(/Weather unavailable/)).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Udupi flood event maps' })).toBeVisible()
  await expect(page.getByText(/Source image:.*DFO_2728/)).toBeVisible()
  await expect(page.getByRole('link', { name: 'CC BY-NC 4.0', exact: true })).toBeVisible()
  for (const id of [2728, 3551]) {
    if (id === 3551) await page.getByLabel('Recorded event').selectOption(String(id))
    await expect(page.getByText(new RegExp(`Source image:.*DFO_${id}`))).toBeVisible()
    const actual = saved(id)
    const response = await page.request.get(`/api/historical-floods/${id}`)
    expect(response.ok()).toBe(true)
    expect((await response.json()).floodwater).toEqual(actual)
    // SVG paths must be the exported polygon rings (one path per raster cell), not markers/circles.
    await expect(page.locator('.historical-map path[fill="#dc6047"]')).toHaveCount(actual.features.length)
    expect(await page.locator('.historical-map circle, .historical-map .leaflet-marker-icon').count()).toBe(0)
    const map = page.getByRole('region', { name: /Historical satellite floodwater/ })
    await map.scrollIntoViewIfNeeded()
    await map.screenshot({ path: `${tmpdir()}/floodpulse-event-${id}.png` })
  }
  expect(errors).toEqual([])
})

test('district view, mobile layout and historical warning remain usable', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto('/')
  await expect(page.getByText(/Source image:.*DFO_2728/)).toBeVisible()
  await page.getByRole('button', { name: 'Show district', exact: true }).click()
  await page.getByRole('button', { name: 'Zoom to mapped water', exact: true }).click()
  await expect(page.getByText(/This is not current flooding/)).toBeVisible()
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
})
