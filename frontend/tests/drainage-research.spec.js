import { expect, test } from '@playwright/test'
import { readFileSync } from 'node:fs'
import { tmpdir } from 'node:os'

const dataset = new URL('../../data/processed/udupi_drainage_gis_v1/', import.meta.url)
const manifest = JSON.parse(readFileSync(new URL('manifest.json', dataset), 'utf8'))

test.beforeEach(async ({ page }) => {
  await page.route('**/*', async route => {
    const url = new URL(route.request().url())
    if (!['127.0.0.1', 'localhost'].includes(url.hostname)) return route.abort()
    if (url.pathname === '/api/weather') return route.fulfill({ status: 503, contentType: 'application/json', body: JSON.stringify({ status: 'unavailable', message: 'Weather isolated in GIS rendering test' }) })
    return route.continue()
  })
})

test('real local raster previews render within Udupi study geography and toggle correctly', async ({ page }) => {
  const errors = []; page.on('pageerror', error => errors.push(error.message))
  await page.goto('/')
  await expect(page.getByText(/Source image:.*DFO_2728/)).toBeVisible()
  await page.getByRole('button', { name: 'Show research layers' }).click()
  const map = page.getByRole('region', { name: 'Udupi drainage research geography' })
  await expect(map).toBeVisible()
  const response = await page.request.get('/api/drainage-research')
  const catalog = await response.json()
  expect(response.ok()).toBe(true)
  expect(catalog.study_area).toEqual(JSON.parse(readFileSync(new URL('study_area.geojson', dataset), 'utf8')))
  expect(catalog.mapped_drains).toEqual(JSON.parse(readFileSync(new URL('mapped_drains.geojson', dataset), 'utf8')))
  const names = { elevation: 'Surface elevation', slope: 'Surface slope', land_cover: 'Land cover (2021)' }
  for (const [key, name] of Object.entries(names)) {
    if (key !== 'elevation') await page.getByLabel(name, { exact: true }).check()
    const image = map.locator('.leaflet-image-layer')
    await expect(image).toHaveCount(1)
    await expect(image).toHaveAttribute('alt', name)
    await expect.poll(() => image.evaluate(el => el.complete && el.naturalWidth > 0)).toBe(true)
    expect(await image.evaluate(el => [el.naturalWidth, el.naturalHeight])).toEqual(manifest.layers[key].preview_dimensions)
    expect(catalog.layers[key].preview_bounds).toEqual(manifest.layers[key].preview_bounds)
    const png = await page.request.get(catalog.layers[key].url)
    expect(await png.body()).toEqual(readFileSync(new URL(`${key}.png`, dataset)))
    const box = await image.boundingBox(), frame = await map.boundingBox()
    expect(box.width).toBeGreaterThan(200); expect(box.height).toBeGreaterThan(200)
    expect(box.x).toBeGreaterThanOrEqual(frame.x-2); expect(box.y).toBeGreaterThanOrEqual(frame.y-2)
    expect(box.x+box.width).toBeLessThanOrEqual(frame.x+frame.width+2)
    expect(box.y+box.height).toBeLessThanOrEqual(frame.y+frame.height+2)
    await map.screenshot({ path: `${tmpdir()}/floodpulse-research-${key}.png` })
  }
  await expect(page.getByLabel(/Mapped drains and ditches/)).toBeDisabled()
  await expect(page.getByText(/does not mean there are no drains/)).toBeVisible()
  await expect(page.getByText(/not an official municipal boundary/)).toBeVisible()
  await expect(page.getByText(/do not incur any liability/)).toBeVisible()
  await page.getByText('Sources, retrieval times and licence conditions').click()
  await expect(page.getByRole('link', { name: 'ODbL 1.0', exact: true })).toBeVisible()
  expect(errors).toEqual([])
})

test('mobile optional research view remains usable with unavailable tiles and unchanged historical map', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto('/')
  await page.getByRole('button', { name: 'Show research layers' }).click()
  await expect(page.getByRole('region', { name: 'Udupi drainage research geography' })).toBeVisible()
  await page.getByLabel('Surface slope', { exact: true }).check()
  await expect(page.getByText(/13.52 degrees/)).toBeVisible()
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
  await page.getByRole('button', { name: 'Hide research layers' }).click()
  await expect(page.getByText(/Source image:.*DFO_2728/)).toBeVisible()
  await expect(page.locator('.historical-map path[fill="#dc6047"]')).toHaveCount(33)
})
