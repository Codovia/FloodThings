import { withoutLiveRisk } from './liveData.js'
import { openTab } from './oneScreen.js'
import {test,expect} from '@playwright/test'
import {emptyShelterDirectory} from './shelterFixture.js'
const weather=()=>({status:'available',retrieved_at:new Date().toISOString(),current:{temperature_c:27,humidity_percent:80,precipitation_mm:0,valid_at:new Date().toISOString(),interval_seconds:900},grid_location:{latitude:13.25,longitude:74.95},forecast:Array.from({length:7},(_,i)=>({date:`2026-10-${10+i}`,weather_code:61,precipitation_mm:i,temperature_min_c:22,temperature_max_c:29}))})
test.beforeEach(async({page})=>{await page.route('**/*',route=>{const u=new URL(route.request().url());if(!['localhost','127.0.0.1'].includes(u.hostname))return route.abort();if(u.pathname==='/api/weather')return route.fulfill({status:200,contentType:'application/json',body:JSON.stringify({...weather(),location:u.searchParams.has('latitude')?{latitude:+u.searchParams.get('latitude'),longitude:+u.searchParams.get('longitude')}:null})});return route.continue()});await emptyShelterDirectory(page)})
test('Home shows statewide fallback, compact summaries and explicit point weather without daily tables',async({page})=>{
 await page.context().clearPermissions();await page.goto('/');await expect(page.getByRole('region',{name:'Karnataka emergency map'})).toBeVisible();await expect(page.getByRole('heading',{name:'Karnataka statewide view'})).toBeVisible();await expect(page.getByLabel('Weather latitude')).toHaveCount(0);await expect(page.getByRole('list',{name:'Daily weather forecasts'})).toHaveCount(0);await expect(page.getByText('No currently verified open shelters are available in this directory.')).toHaveCount(0)
 await page.getByRole('button',{name:'Search districts and localities'}).focus();await page.keyboard.press('Enter');await expect(page.getByLabel('Karnataka district')).toBeVisible();await page.context().grantPermissions(['geolocation']);await page.context().setGeolocation({latitude:14,longitude:75,accuracy:40});await page.getByRole('button',{name:'Use my location'}).click();await expect(page.getByRole('heading',{name:'GPS-selected point',exact:true})).toBeVisible();await expect(page.getByRole('heading',{name:'27 °C',exact:true})).toBeVisible();await expect(page.locator('#risk-area-title')).toHaveText('Flood & drainage risk · next 24 h')
})
test('Home weather and Shelters prioritize their own content, with independent point controls on mobile',async({page,context})=>{
 // Phones: the seven-day forecast is Home's Weather tab (the Weather page was merged into Home); no coordinate form, no weather map.
 await page.setViewportSize({width:390,height:844});await context.grantPermissions(['geolocation']);await context.setGeolocation({latitude:14,longitude:75,accuracy:40})
 await page.goto('/');await expect(page.getByText('27 °C',{exact:true})).toBeVisible();await expect(page.getByLabel('Weather latitude')).toHaveCount(0)
 await openTab(page,'Weather');await expect(page.getByRole('list',{name:'Daily weather forecasts'}).getByRole('article')).toHaveCount(4)
 await expect(page.getByRole('region',{name:'Weather location selection map'})).toHaveCount(0)
 await page.getByRole('button',{name:'Open navigation menu'}).click();await page.getByRole('navigation',{name:'Main navigation'}).getByRole('link',{name:'Shelters',exact:true}).click();await expect(page.getByText('No currently verified open shelters are available in this directory.')).toBeVisible();await expect(page.getByLabel('Weather latitude')).toHaveCount(0);await expect(page.getByRole('list',{name:'Daily weather forecasts'})).not.toBeVisible()
 await page.getByRole('button',{name:'Change location'}).click();await expect(page.getByRole('dialog',{name:'Change location'}).getByRole('button',{name:'Search districts and localities'})).toBeVisible();await page.getByRole('button',{name:'Close',exact:true}).click()
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true)
})
test('tile failure retains exact evidence polygons and stops background requests rather than retrying',async({page})=>{
 await page.goto('/flood-map');await expect(page.locator('.intelligence-map path[fill="#dc6047"]')).toHaveCount(56);await expect(page.getByText(/Background tiles are unavailable/)).toBeVisible();await expect(page.locator('.intelligence-map img.leaflet-tile')).toHaveCount(0);await page.getByLabel('Go to district',{exact:true}).selectOption('nic:udupi.nic.in');await expect(page.locator('.intelligence-map path[fill="#dc6047"]')).toHaveCount(56);await openTab(page,'Past floods');await page.locator('.intelligence-map path[fill="#dc6047"]').first().dispatchEvent('click');await expect(page.getByRole('dialog',{name:'Flood evidence details'})).toBeVisible();await expect(page.getByRole('dialog').getByText(/Global Flood Database event \d+/)).toBeVisible();await expect(page.getByRole('dialog').getByText(/not current flooding/)).toBeVisible()
})
test('tile DOM carries origin-only identification while application response keeps its privacy header',async({page})=>{
 // Avoid a deliberate failure for this test, while making zero external requests.
 await page.route('https://tile.openstreetmap.org/**',route=>route.fulfill({status:200,contentType:'image/png',body:Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aS1cAAAAASUVORK5CYII=','base64')}));
 const response=await page.goto('/flood-map');expect(response.headers()['referrer-policy']).toBe('same-origin');await expect(page.locator('.intelligence-map img.leaflet-tile').first()).toHaveAttribute('referrerpolicy','origin');await expect(page.locator('.intelligence-map .leaflet-control-attribution')).toContainText('OpenStreetMap');await expect(page.locator('.intelligence-map path[fill="#dc6047"]')).toHaveCount(56)
})

// Not a risk test: answer live-risk requests in the browser (see liveData.js). Registered last, so it runs first.
test.beforeEach(async ({ page }) => { await withoutLiveRisk(page) })
