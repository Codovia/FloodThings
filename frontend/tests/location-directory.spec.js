import { withoutLiveRisk } from './liveData.js'
import { openTab } from './oneScreen.js'
import { choosePlaceForHome, GPS_POINT_NAME } from './pointSelection.js'
import { expect, test } from '@playwright/test'

// Directory endpoints and map geography are genuine retained public records.
// Weather fixtures remain only in browser memory; no external requests.
const body = (point, retrieved) => ({ status: 'available', location: point, retrieved_at: retrieved,
  current: { temperature_c: 27, humidity_percent: 70, precipitation_mm: 0, interval_seconds: 900, valid_at: retrieved, stale: false },
  forecast: Array.from({ length: 7 }, (_, i) => ({ date: `2026-10-${String(8+i).padStart(2,'0')}`, temperature_min_c: 20, temperature_max_c: 30, precipitation_mm: i, weather_code: 61 })),
  grid_location: { latitude: 13.25, longitude: 74.95 }, prediction_status: 'not_available' })
// Home (which now shows the weather) has the place search as a button; it closes after each choice and lists four results per page.
const open = async page => {
  if (!await page.getByRole('button', { name: 'Close place search' }).count()) await page.getByRole('button', { name: 'Search districts and localities' }).click()
  await expect(page.getByLabel('Karnataka district')).toBeEnabled()
}
async function locality(page, name) {
  const list = page.getByRole('list', { name: 'District localities' }), target = list.getByRole('button', { name: new RegExp(`^${name} —`) })
  await expect(list.getByRole('button').first()).toBeVisible()
  const pager = page.getByRole('navigation', { name: 'More localities' })
  if (await pager.count()) while (await pager.getByRole('button', { name: '‹ Previous' }).isEnabled()) await pager.getByRole('button', { name: '‹ Previous' }).click()
  while (!await target.count() && await pager.count() && await pager.getByRole('button', { name: 'Next ›' }).isEnabled()) await pager.getByRole('button', { name: 'Next ›' }).click()
  return target
}
const choose = async (page, name) => { await open(page); await (await locality(page, name)).click() }
const homeMap = page => page.getByRole('region', { name: 'Karnataka emergency map' })
const selectedMarker = page => homeMap(page).locator('path[fill="#087e7c"]')   // Home map's selected-place marker
async function weatherDetails(page, text) {
  await page.getByRole('button', { name: 'Details' }).click()
  const dialog = page.getByRole('dialog', { name: 'Weather details & sources' })
  await expect(dialog).toContainText(text); await dialog.getByRole('button', { name: 'Close' }).click()
}

test.beforeEach(async ({ page }) => {
  await page.clock.install({ time: new Date('2026-10-08T06:00:00Z') })
  await page.clock.pauseAt(new Date('2026-10-08T06:00:00Z'))
  await page.route('**/*', async route => {
    const url = new URL(route.request().url())
    if (!['127.0.0.1','localhost'].includes(url.hostname)) return route.abort()
    if (url.pathname === '/api/weather') {
      const point = url.searchParams.has('latitude') ? { latitude: +url.searchParams.get('latitude'), longitude: +url.searchParams.get('longitude') } : null
      return route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(body(point, await page.evaluate(() => new Date().toISOString())))})
    }
    return route.continue()
  })
})

test('real district/locality directory selects exact OSM points, recenters Leaflet, preserves seven days and six-hour refresh', async ({ page }) => {
  // The six-hour cycle applies when the provider's reading is not advancing: this reply's reading is 61 min older than
  // retrieval (under the 90-min notice), so the hourly current-conditions refresh (tested below for Kundapur) does not apply.
  await page.route('**/api/weather*', async route => {
    const url = new URL(route.request().url()), retrieved = await page.evaluate(() => new Date().toISOString())
    const point = url.searchParams.has('latitude') ? { latitude: +url.searchParams.get('latitude'), longitude: +url.searchParams.get('longitude') } : null
    const reply = body(point, retrieved); reply.current.valid_at = new Date(Date.parse(retrieved) - 61 * 60000).toISOString()
    return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(reply) })
  })
  const errors = []; page.on('pageerror',e=>errors.push(e.message)); let calls=0
  page.on('request',r=>{ if(new URL(r.url()).pathname==='/api/weather') calls++ })
  await page.goto('/'); await open(page)
  await expect(page.getByLabel('Karnataka district').locator('option')).toHaveCount(32)
  await page.getByLabel('Karnataka district').selectOption('nic:udupi.nic.in')
  await expect(page.getByRole('status',{name:'District locality results'})).toContainText('5 locality records')
  await expect(page.getByRole('list',{name:'District localities'}).getByRole('button')).toHaveCount(4)
  expect(calls).toBe(0)   // no weather before a place is chosen
  await expect(await locality(page,'Kaup')).toBeDisabled()
  await expect(await locality(page,'Kundapur')).toBeEnabled()
  const request = page.waitForRequest(r=>r.url().includes('latitude=13.2145414&longitude=74.9951861'))
  await choose(page,'Karkala'); await request
  await expect(page.getByRole('heading',{name:'Karkala, Udupi',exact:true})).toBeVisible()
  await weatherDetails(page,'Requested point: 13.2145414')
  // Home's map moves to the chosen place (it frames the area around it, with nearby risk spots): the marker is in view.
  await expect(selectedMarker(page)).toBeInViewport()
  await weatherDetails(page,'13.25°, 74.95°')
  await expect(page.getByRole('list',{name:'Daily weather forecasts'}).getByRole('article')).toHaveCount(7)
  await expect(page.getByRole('status',{name:'Weather data freshness'})).toHaveAttribute('data-freshness','fresh')
  const before=calls; await page.clock.fastForward(6*60*60*1000-1); expect(calls).toBe(before)
  await page.clock.fastForward(1); await expect.poll(()=>calls).toBe(before+1)
  await choose(page,'Udupi')
  await expect(page.getByRole('heading',{name:'Udupi, Udupi',exact:true})).toBeVisible()
  await weatherDetails(page,'Requested point: 13.3419169')
  expect(errors).toEqual([])
})

test('v2 settlement expansion preserves stable Kundapur identity and cross-district weather freshness', async ({ page }) => {
  const requests=[]; page.on('request',r=>{if(new URL(r.url()).pathname==='/api/weather') requests.push(r.url())})
  await page.goto('/'); await open(page); await page.getByLabel('Karnataka district').selectOption('nic:udupi.nic.in')
  await expect(page.getByText(/5 localities/)).toBeVisible()
  await choose(page,'Kundapur')
  await expect(page.getByRole('heading',{name:'Kundapur, Udupi',exact:true})).toBeVisible()
  await weatherDetails(page,'Requested point: 13.6250993')
  await choose(page,'Saligrama')
  await expect(page.getByRole('heading',{name:'Saligrama, Udupi',exact:true})).toBeVisible()
  await weatherDetails(page,'Requested point: 13.4977795')
  await page.clock.fastForward(60*60*1000)
  await open(page); await page.getByLabel('Karnataka district').selectOption('nic:dk.nic.in')
  await expect(page.getByRole('heading',{name:'Saligrama, Udupi',exact:true})).toBeVisible()
  await choose(page,'Mangaluru')
  await expect(page.getByRole('heading',{name:'Mangaluru, Dakshina Kannada',exact:true})).toBeVisible()
  await weatherDetails(page,'Requested point: 12.8698101')
  await expect(selectedMarker(page)).toBeInViewport()
  await expect(page.getByRole('list',{name:'Daily weather forecasts'}).getByRole('article')).toHaveCount(7)
  // Current conditions are re-fetched 60 minutes after their valid time, for the selected point only.
  const before=requests.length; await page.clock.fastForward(60*60*1000-1); expect(requests.length).toBe(before)
  await page.clock.fastForward(1); await expect.poll(()=>requests.length).toBe(before+1)
  expect(requests.at(-1)).toContain('latitude=12.8698101&longitude=74.8430082')
  await expect(page.getByRole('status',{name:'Weather data freshness'})).toHaveAttribute('data-freshness','fresh')
})

test('mobile alias search selects real Mangaluru and disabled Kaup explains unavailable point', async ({ page }) => {
  await page.setViewportSize({width:390,height:844}); await page.goto('/'); await open(page)
  await page.getByLabel('Search districts or localities').fill('Mangalore'); await page.clock.fastForward(250)
  const result=page.getByRole('list',{name:'Place search results'}).getByRole('button',{name:/^Mangaluru — Dakshina Kannada/})
  await expect(result).toBeVisible(); await result.focus(); await page.keyboard.press('Enter')
  await expect(page.getByRole('heading',{name:'Mangaluru, Dakshina Kannada',exact:true})).toBeVisible()
  await open(page); await page.getByLabel('Karnataka district').selectOption('nic:udupi.nic.in')
  const disabled=await locality(page,'Kaup')
  await expect(disabled).toBeDisabled(); await expect(disabled).toHaveAttribute('aria-describedby',/unavailable-district-udupi-admin:municipality:kaup$/);const description=await disabled.getAttribute('aria-describedby');await expect(page.locator('[id='+JSON.stringify(description)+']')).toContainText('settlement-node coordinate was not reviewed')
  await expect(page.getByText(/settlement-node coordinate was not reviewed/)).toBeVisible()
  await page.getByLabel('Search localities in Udupi').fill('A very long unlisted settlement name');await page.clock.fastForward(250)
  await expect(page.getByRole('status',{name:'District locality results'})).toContainText('No verified localities')
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true)
})

test('keyboard global search, district filtering, empty states and mobile focus remain usable', async ({ page }) => {
  await page.setViewportSize({width:390,height:844}); await page.goto('/')
  const button = page.getByRole('button',{name:'Search districts and localities'})
  await button.focus(); await page.keyboard.press('Enter')
  await expect(page.getByLabel('Karnataka district')).toBeEnabled()
  await page.getByLabel('Search districts or localities').fill('Karkala'); await page.clock.fastForward(250)
  const result = page.getByRole('list',{name:'Place search results'}).getByRole('button',{name:/^Karkala —/})
  await expect(result).toBeVisible(); await result.focus(); await page.keyboard.press('Enter')
  await expect(page.getByRole('heading',{name:'Karkala, Udupi'})).toBeVisible()
  await open(page); const search = page.getByLabel('Search localities in Udupi'); await search.fill('Unlisted'); await page.clock.fastForward(250)
  await expect(page.getByRole('status',{name:'District locality results'})).toContainText('No verified localities')
  await page.getByLabel('Karnataka district').selectOption('nic:ballari.nic.in')
  await expect(page.getByText(/a district alone has no single weather point/)).toBeVisible()
  await expect(page.getByRole('heading',{name:'Karkala, Udupi'})).toBeVisible()
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true)
  await page.getByLabel('Search districts or localities').focus()
  expect(await page.getByLabel('Search districts or localities').evaluate(el=>getComputedStyle(el).outlineStyle)).not.toBe('none')
})

test('directory unavailable and locality provider failure preserve manual recovery without fabricated weather', async ({ page }) => {
  await page.route('**/api/locations/districts',route=>route.fulfill({status:503,contentType:'application/json',body:JSON.stringify({detail:'Controlled directory outage'})}))
  await page.goto('/'); await page.getByRole('button',{name:'Search districts and localities'}).click()
  await expect(page.getByRole('alert',{name:'Location directory error'})).toContainText('Controlled directory outage')
  await page.unroute('**/api/locations/districts'); await page.getByRole('button',{name:'Retry location search'}).click()
  await expect(page.getByLabel('Karnataka district')).toBeEnabled(); await page.getByLabel('Karnataka district').selectOption('nic:udupi.nic.in')
  await page.route('**/api/weather?**',route=>route.fulfill({status:503,contentType:'application/json',body:JSON.stringify({status:'unavailable',message:'Controlled provider failure'})}))
  await choose(page,'Karkala'); await expect(page.getByText(/Controlled provider failure/)).toBeVisible()
  await expect(page.getByRole('heading',{name:'Karkala, Udupi'})).toBeVisible(); await expect(page.getByText('27 °C',{exact:true})).toHaveCount(0)

  await choosePlaceForHome(page,14,75); await expect(page.getByRole('heading',{name:GPS_POINT_NAME})).toBeVisible()
})

test('late locality weather cannot overwrite newer locality during point switching', async ({ page }) => {
  let release
  await page.route('**/api/weather?latitude=13.2145414&longitude=74.9951861',async route=>{ await new Promise(resolve=>{release=resolve}); try { await route.fulfill({status:200,contentType:'application/json',body:JSON.stringify({...body({latitude:13.2145414,longitude:74.9951861},'2026-10-08T06:00:00Z'),current:{temperature_c:99}})}) } catch {} })
  await page.goto('/'); await open(page); await page.getByLabel('Karnataka district').selectOption('nic:udupi.nic.in')
  const old=page.waitForRequest(r=>r.url().includes('latitude=13.2145414'))
  await choose(page,'Karkala'); await old; await choose(page,'Udupi')
  await expect(page.getByRole('heading',{name:'Udupi, Udupi'})).toBeVisible(); await expect(page.getByText('27 °C',{exact:true})).toBeVisible()
  release(); await expect(page.getByText('99 °C',{exact:true})).toHaveCount(0)
  await weatherDetails(page,'Requested point: 13.3419169')
})

test('database directory outage leaves manual point weather and seven-day freshness independent', async ({ page }) => {
  await page.route('**/api/locations/**', route => route.fulfill({status:503,contentType:'application/json',body:JSON.stringify({detail:'Location database is unavailable or invalid; no file fallback was used'})}))
  await page.goto('/'); await page.getByRole('button',{name:'Search districts and localities'}).click()
  await expect(page.getByRole('alert',{name:'Location directory error'})).toContainText('Location database is unavailable')

  const request=page.waitForRequest(r=>r.url().includes('latitude=14&longitude=75'))
  await choosePlaceForHome(page,14,75); await request
  await expect(page.getByRole('heading',{name:GPS_POINT_NAME})).toBeVisible()
  await expect(page.getByRole('list',{name:'Daily weather forecasts'}).getByRole('article')).toHaveCount(7)
  await expect(page.getByRole('status',{name:'Weather data freshness'})).toHaveAttribute('data-freshness','fresh')
  await page.getByRole('button',{name:'Search districts and localities'}).click()
  await expect(page.getByRole('alert',{name:'Location directory error'})).toBeVisible()
})

// Not a risk test: answer live-risk requests in the browser (see liveData.js). Registered last, so it runs first.
test.beforeEach(async ({ page }) => { await withoutLiveRisk(page) })
