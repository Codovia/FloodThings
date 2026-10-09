import { expect, test } from '@playwright/test'

// Directory endpoints and map geography are genuine retained public records.
// Weather fixtures remain only in browser memory; no external requests.
const body = (point, retrieved) => ({ status: 'available', location: point, retrieved_at: retrieved,
  current: { temperature_c: 27, humidity_percent: 70, precipitation_mm: 0, interval_seconds: 900, valid_at: retrieved, stale: false },
  forecast: Array.from({ length: 7 }, (_, i) => ({ date: `2026-10-${String(8+i).padStart(2,'0')}`, temperature_min_c: 20, temperature_max_c: 30, precipitation_mm: i, weather_code: 61 })),
  grid_location: { latitude: 13.25, longitude: 74.95 }, prediction_status: 'not_available' })
const open = async page => { await page.getByRole('button', { name: 'Search districts and localities' }).click(); await expect(page.getByLabel('Karnataka district')).toBeEnabled() }
const choose = (page, name) => page.getByRole('list', { name: 'District localities' }).getByRole('button', { name: new RegExp(`^${name} —`) }).click()

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
  const errors = []; page.on('pageerror',e=>errors.push(e.message)); let calls=0
  page.on('request',r=>{ if(new URL(r.url()).pathname==='/api/weather') calls++ })
  await page.goto('/'); await expect(page.getByText('27 °C',{exact:true})).toBeVisible(); await open(page)
  await expect(page.getByLabel('Karnataka district').locator('option')).toHaveCount(32)
  await page.getByLabel('Karnataka district').selectOption('nic:udupi.nic.in')
  await expect(page.getByRole('list',{name:'District localities'}).getByRole('button')).toHaveCount(5)
  expect(calls).toBe(1)
  await expect(page.getByRole('button',{name:/^Kaup —/})).toBeDisabled()
  await expect(page.getByRole('button',{name:/^Kundapur —/})).toBeEnabled()
  const request = page.waitForRequest(r=>r.url().includes('latitude=13.2145414&longitude=74.9951861'))
  await choose(page,'Karkala'); await request
  await expect(page.getByRole('heading',{name:'Karkala, Udupi',exact:true})).toBeVisible()
  await expect(page.getByText(/Requested point: 13.2145414/)).toBeVisible()
  const map = page.getByRole('region',{name:'Weather location selection map'})
  // Actual Leaflet marker is visible in the recentered viewport, not offscreen.
  await map.scrollIntoViewIfNeeded()
  await expect(map.locator('path.leaflet-interactive')).toBeInViewport()
  const centred = await map.evaluate(el => { const a=el.getBoundingClientRect(), b=el.querySelector('path.leaflet-interactive').getBoundingClientRect(); return Math.abs((a.left+a.right-b.left-b.right)/2)<3 && Math.abs((a.top+a.bottom-b.top-b.bottom)/2)<3 })
  expect(centred).toBe(true)
  await expect(page.getByText('Latitude 13.25°, longitude 74.95°')).toBeVisible()
  await expect(page.getByRole('list',{name:'Daily weather forecasts'}).getByRole('article')).toHaveCount(7)
  await expect(page.getByRole('status',{name:'Weather data freshness'})).toHaveAttribute('data-freshness','fresh')
  const before=calls; await page.clock.fastForward(6*60*60*1000-1); expect(calls).toBe(before)
  await page.clock.fastForward(1); await expect.poll(()=>calls).toBe(before+1)
  await choose(page,'Udupi')
  await expect(page.getByRole('heading',{name:'Udupi, Udupi',exact:true})).toBeVisible()
  await expect(page.getByText(/Requested point: 13.3419169/)).toBeVisible()
  await expect(page.getByText(/Flood prediction is not available/)).toBeVisible()
  expect(errors).toEqual([])
})

test('v2 settlement expansion preserves stable Kundapur identity and cross-district weather freshness', async ({ page }) => {
  const requests=[]; page.on('request',r=>{if(new URL(r.url()).pathname==='/api/weather') requests.push(r.url())})
  await page.goto('/'); await open(page); await page.getByLabel('Karnataka district').selectOption('nic:udupi.nic.in')
  await expect(page.getByText(/5 selectable mapped localities across 2 districts/)).toBeVisible()
  await choose(page,'Kundapur')
  await expect(page.getByRole('heading',{name:'Kundapur, Udupi',exact:true})).toBeVisible()
  await expect(page.getByText(/Requested point: 13.6250993/)).toBeVisible()
  await choose(page,'Saligrama')
  await expect(page.getByRole('heading',{name:'Saligrama, Udupi',exact:true})).toBeVisible()
  await expect(page.getByText(/Requested point: 13.4977795/)).toBeVisible()
  await page.clock.fastForward(60*60*1000)
  await page.getByLabel('Karnataka district').selectOption('nic:dk.nic.in')
  await expect(page.getByRole('heading',{name:'Saligrama, Udupi',exact:true})).toBeVisible()
  await choose(page,'Mangaluru')
  await expect(page.getByRole('heading',{name:'Mangaluru, Dakshina Kannada',exact:true})).toBeVisible()
  await expect(page.getByText(/Requested point: 12.8698101/)).toBeVisible()
  const map=page.getByRole('region',{name:'Weather location selection map'})
  await map.scrollIntoViewIfNeeded(); await expect(map.locator('path.leaflet-interactive')).toBeInViewport()
  expect(await map.evaluate(el=>{const a=el.getBoundingClientRect(),b=el.querySelector('path.leaflet-interactive').getBoundingClientRect();return Math.abs((a.left+a.right-b.left-b.right)/2)<3&&Math.abs((a.top+a.bottom-b.top-b.bottom)/2)<3})).toBe(true)
  await expect(page.getByRole('list',{name:'Daily weather forecasts'}).getByRole('article')).toHaveCount(7)
  const before=requests.length; await page.clock.fastForward(5*60*60*1000); expect(requests.length).toBe(before)
  await page.clock.fastForward(60*60*1000); await expect.poll(()=>requests.length).toBe(before+1)
  expect(requests.at(-1)).toContain('latitude=12.8698101&longitude=74.8430082')
  await expect(page.getByRole('status',{name:'Weather data freshness'})).toHaveAttribute('data-freshness','fresh')
  await expect(page.getByText(/Flood prediction is not available/)).toBeVisible()
})

test('mobile alias search selects real Mangaluru and disabled Kaup explains unavailable point', async ({ page }) => {
  await page.setViewportSize({width:390,height:844}); await page.goto('/'); await open(page)
  await page.getByLabel('Search districts or localities').fill('Mangalore'); await page.clock.fastForward(250)
  const result=page.getByRole('list',{name:'Place search results'}).getByRole('button',{name:/^Mangaluru — Dakshina Kannada/})
  await expect(result).toBeVisible(); await result.focus(); await page.keyboard.press('Enter')
  await expect(page.getByRole('heading',{name:'Mangaluru, Dakshina Kannada',exact:true})).toBeVisible()
  await page.getByLabel('Karnataka district').selectOption('nic:udupi.nic.in')
  const disabled=page.getByRole('button',{name:/^Kaup —/})
  await expect(disabled).toBeDisabled(); await expect(disabled).toHaveAttribute('aria-describedby','unavailable-district-udupi-admin:municipality:kaup')
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
  const search = page.getByLabel('Search localities in Udupi'); await search.fill('Unlisted'); await page.clock.fastForward(250)
  await expect(page.getByRole('status',{name:'District locality results'})).toContainText('No verified localities')
  await page.getByLabel('Karnataka district').selectOption('nic:ballari.nic.in')
  await expect(page.getByText(/Verified public navigation geometry and a representative point are unavailable/)).toBeVisible()
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
  await page.getByLabel('Weather latitude').fill('14'); await page.getByLabel('Weather longitude').fill('75')
  await page.getByRole('button',{name:'Get point weather'}).click(); await expect(page.getByRole('heading',{name:'Entered coordinates'})).toBeVisible()
})

test('late locality weather cannot overwrite newer locality during point switching', async ({ page }) => {
  let release
  await page.route('**/api/weather?latitude=13.2145414&longitude=74.9951861',async route=>{ await new Promise(resolve=>{release=resolve}); try { await route.fulfill({status:200,contentType:'application/json',body:JSON.stringify({...body({latitude:13.2145414,longitude:74.9951861},'2026-10-08T06:00:00Z'),current:{temperature_c:99}})}) } catch {} })
  await page.goto('/'); await open(page); await page.getByLabel('Karnataka district').selectOption('nic:udupi.nic.in')
  const old=page.waitForRequest(r=>r.url().includes('latitude=13.2145414'))
  await choose(page,'Karkala'); await old; await choose(page,'Udupi')
  await expect(page.getByRole('heading',{name:'Udupi, Udupi'})).toBeVisible(); await expect(page.getByText('27 °C',{exact:true})).toBeVisible()
  release(); await expect(page.getByText('99 °C',{exact:true})).toHaveCount(0)
  await expect(page.getByText(/Requested point: 13.3419169/)).toBeVisible()
})
