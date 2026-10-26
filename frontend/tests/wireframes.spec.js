import {test,expect} from '@playwright/test'
import {emptyShelterDirectory} from './shelterFixture.js'
import {openTab,expectOneScreen} from './oneScreen.js'

// No external services or operational writes in these layout/state tests.
test.beforeEach(async({page})=>{
 await page.route('**/*',route=>{
  const url=new URL(route.request().url());if(!['127.0.0.1','localhost'].includes(url.hostname))return route.abort()
  if(url.pathname==='/api/weather')return route.fulfill({status:200,contentType:'application/json',body:JSON.stringify({status:'available',retrieved_at:new Date().toISOString(),location:{latitude:+(url.searchParams.get('latitude')||12.9767936),longitude:+(url.searchParams.get('longitude')||77.590082)},grid_location:{latitude:13.25,longitude:74.95},current:{temperature_c:27,humidity_percent:80,precipitation_mm:0,valid_at:new Date().toISOString(),interval_seconds:900},forecast:Array.from({length:7},(_,i)=>({date:`2026-10-${10+i}`,weather_code:61,precipitation_mm:i,temperature_min_c:22,temperature_max_c:29}))})})
  return route.continue()
 })
 await emptyShelterDirectory(page)
})
test('sketches 1-3 have information left and a dominant map right at both desktop sizes',async({page})=>{
 for(const size of [{width:1366,height:768},{width:1920,height:1080}]){
  await page.setViewportSize(size)
  for(const route of ['/','/shelters']){
   // Home uses its own status/map grid (and now holds the weather); Shelters uses the shared workspace.
   await page.goto(route);const information=page.locator(route==='/'?'.home-essential-status':'.workspace-information'),map=page.locator(route==='/'?'.home-map-stage':'.workspace-map')
   await expect(map).toBeVisible();const left=await information.boundingBox(),right=await map.boundingBox()
   expect(right.x).toBeGreaterThan(left.x+left.width);expect(right.width).toBeGreaterThan(left.width)
   expect(right.height).toBeGreaterThan(350)
   expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true)
   await page.waitForTimeout(1600);expect(await expectOneScreen(page),`${route} ${size.width}`).toEqual({page:0,width:0,scrolls:0,outside:0})
  }
 }
})
test('district selection survives all public routes; a historical cell never changes weather coordinates',async({page})=>{
 let weatherRequests=0;page.on('request',r=>{if(new URL(r.url()).pathname==='/api/weather')weatherRequests++})
 await page.context().clearPermissions();await page.goto('/');await page.getByRole('button',{name:'Search districts and localities'}).click()
 await page.getByLabel('Karnataka district',{exact:true}).selectOption('nic:udupi.nic.in')
 await page.getByRole('button',{name:'Close place search'}).click()
 const nav=page.getByRole('navigation',{name:'Main navigation'})
 await nav.getByRole('link',{name:'Flood Map',exact:true}).click();await expect(page.getByLabel('Go to district')).toHaveValue('nic:udupi.nic.in')
 await page.getByRole('button',{name:'Zoom to past floods',exact:true}).click();await page.locator('.intelligence-map path[fill="#dc6047"]').first().click({force:true});await expect(page.getByRole('dialog',{name:'Flood evidence details'})).toBeVisible()
 expect(weatherRequests).toBe(0)   // a district alone has no weather point
 await page.getByRole('button',{name:'Close',exact:true}).click()
 await nav.getByRole('link',{name:'Shelters',exact:true}).click()
 await page.getByRole('button',{name:'Change location'}).click();await page.getByRole('button',{name:'Search districts and localities'}).click()
 await expect(page.getByLabel('Karnataka district',{exact:true})).toHaveValue('nic:udupi.nic.in')
 await page.getByRole('button',{name:'Close',exact:true}).click()
 await expect(page.getByText('No currently verified open shelters are available in this directory.')).toBeVisible()
 // An old /weather link opens Home; the district filter is kept and no weather point is invented.
 await page.evaluate(()=>{history.pushState(null,'','/weather');dispatchEvent(new PopStateEvent('popstate'))});await expect(page).toHaveURL(/\/$/)
 await expect(page.getByRole('heading',{name:'Karnataka statewide view',exact:true})).toBeVisible();expect(weatherRequests).toBe(0)
 await expect(page.getByRole('button',{name:'Run experimental rainfall model'})).toHaveCount(0)
})
test('mobile splits Home into Warnings/Risk/Map tabs, and exposes honest warning and hazard states',async({page})=>{
 await page.setViewportSize({width:390,height:844});await page.goto('/')
 await expect(page.locator('.imd-card')).toBeVisible()
 await openTab(page,'Risk');await expect(page.getByText(/Choose your town or use your location to see the riskiest spots/)).toBeVisible()
 await openTab(page,'Map');await expect(page.getByRole('region',{name:'Karnataka emergency map'})).toBeVisible()
 await page.getByRole('button',{name:'Open navigation menu'}).click();await page.getByRole('navigation',{name:'Main navigation'}).getByRole('link',{name:'Flood Map',exact:true}).click()
 await openTab(page,'Sources')
 await expect(page.getByText('No verified potential flood-prone zone dataset is available, so no flood-prone zones are shown.',{exact:false})).toBeVisible()
 // On phones the map is its own tab; past-flood polygons must be drawn once it is shown.
 await openTab(page,'Map');await expect(page.locator('.intelligence-map path[fill="#dc6047"]')).toHaveCount(56)
})
