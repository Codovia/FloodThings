import { test, expect } from '@playwright/test'
async function setup(page, mode='pending') {
 const requests=[]
 if(mode!=='native')await page.clock.install({time:new Date('2026-10-12T06:00:00Z')})
 await page.addInitScript(mode=>{
  window.__gpsCalls=0;window.__watchCalls=0
  if(mode==='native')return
  if(mode==='unsupported'){Object.defineProperty(navigator,'geolocation',{value:undefined});return}
  if(mode==='insecure')Object.defineProperty(window,'isSecureContext',{value:false})
  Object.defineProperty(navigator,'geolocation',{value:{getCurrentPosition:(yes,no,options)=>{window.__gpsCalls++;window.__gpsSuccess=yes;window.__gpsFailure=no;window.__gpsOptions=options;if(mode==='denied')no({code:1});if(mode==='unavailable')no({code:2})},watchPosition:()=>window.__watchCalls++}})
 },mode)
 await page.route('**/*',async route=>{
  const u=new URL(route.request().url());if(!['127.0.0.1','localhost'].includes(u.hostname))return route.abort()
  if(u.pathname==='/api/weather'){
   requests.push(u.search);const stamp=await page.evaluate(()=>new Date().toISOString()),location={latitude:+u.searchParams.get('latitude'),longitude:+u.searchParams.get('longitude')}
   return route.fulfill({status:200,contentType:'application/json',body:JSON.stringify({status:'available',location,grid_location:location,retrieved_at:stamp,current:{valid_at:stamp,temperature_c:27,precipitation_mm:0,interval_seconds:900},forecast_coverage:{day_definition:'local_calendar_day',timezone:'Asia/Kolkata'},forecast_units:{precipitation_mm:'mm'},forecast:Array.from({length:7},(_,i)=>({date:`2026-10-${12+i}`,precipitation_mm:i,temperature_min_c:22,temperature_max_c:29,weather_code:61}))})})
  }
  return route.continue()
 })
 return requests
}
async function locate(page,latitude=13.34,longitude=74.74,accuracy=40){await page.evaluate(({latitude,longitude,accuracy})=>window.__gpsSuccess({coords:{latitude,longitude,accuracy},timestamp:Date.now()}),{latitude,longitude,accuracy})}
const nav=page=>page.getByRole('navigation',{name:'Main navigation'})
test('automatic GPS uses exact coordinates, browser accuracy and one weather session across routes',async({page})=>{
 const requests=await setup(page);await page.goto('/');await expect(page.getByRole('region',{name:'Karnataka emergency map'})).toBeVisible();expect(requests).toHaveLength(0)
 await locate(page,13.34261,74.74953);await expect(page.getByRole('heading',{name:'27 °C',exact:true})).toBeVisible();expect(requests).toEqual(['?latitude=13.34261&longitude=74.74953'])
 await expect(page.getByText(/Browser-reported accuracy: ±40 m/)).toBeVisible();await expect(page.getByRole('heading',{name:'Flood & drainage risk · next 24 h'})).toBeVisible();await expect(page.getByLabel('Current weather and rain')).toContainText('Unavailable rain forecast in the next 24 h')
 expect(await page.evaluate(()=>window.__gpsOptions)).toEqual({enableHighAccuracy:true,timeout:10000,maximumAge:0})
 await page.evaluate(()=>{history.pushState(null,'','/weather');dispatchEvent(new PopStateEvent('popstate'))});await expect(page.getByRole('heading',{name:'GPS-selected point'})).toBeVisible();expect(requests).toHaveLength(1)
 await nav(page).getByRole('link',{name:'Home',exact:true}).click();await expect(page.getByRole('heading',{name:'GPS-selected point'})).toBeVisible();expect(await page.evaluate(()=>window.__gpsCalls)).toBe(1);expect(await page.evaluate(()=>window.__watchCalls)).toBe(0);expect(requests).toHaveLength(1)
 expect(new URL(page.url()).search).toBe('');expect(await page.evaluate(()=>Object.keys(sessionStorage).concat(Object.keys(localStorage)).filter(k=>/gps|latitude|longitude/i.test(k)))).toEqual([])
})
for(const [mode,text] of [['denied','Location permission was denied'],['unavailable','Location could not be determined'],['unsupported','Location access is unavailable in this browser'],['insecure','Location requires a secure connection']])test(`${mode} retains statewide map and name search without default weather`,async({page})=>{
 const requests=await setup(page,mode);await page.goto('/');await expect(page.getByText(text,{exact:false})).toBeVisible();await expect(page.getByRole('heading',{name:'Karnataka statewide view'})).toBeVisible();await expect(page.getByRole('region',{name:'Karnataka emergency map'})).toBeVisible();await expect(page.getByRole('button',{name:'Search districts and localities'})).toBeVisible();expect(requests).toHaveLength(0)
})
test('bounded timeout discards a late browser result',async({page})=>{
 const requests=await setup(page);await page.goto('/');await page.clock.fastForward(10001);await expect(page.getByText(/Location request timed out/)).toBeVisible();await locate(page);await expect(page.getByRole('heading',{name:'Karnataka statewide view'})).toBeVisible();expect(requests).toHaveLength(0)
})
test('outside-state GPS, including Goa, is explained without snapping to a reviewed locality',async({page})=>{
 const requests=await setup(page);await page.goto('/');await locate(page,15.49,73.83);await expect(page.getByText(/Your location is outside Karnataka/).first()).toBeVisible();await expect(page.getByRole('heading',{name:'27 °C'})).toBeVisible();expect(requests).toEqual(['?latitude=15.49&longitude=73.83'])
})
test('district-only selection cancels late GPS; verified locality then chooses its own exact point',async({page})=>{
 const requests=await setup(page);await page.goto('/');await page.getByRole('button',{name:'Search districts and localities'}).click();await page.getByLabel('Karnataka district',{exact:true}).selectOption('nic:udupi.nic.in')
 await locate(page,14,75);await expect(page.getByRole('heading',{name:'Karnataka statewide view'})).toBeVisible();expect(requests).toHaveLength(0)
 await page.getByRole('button',{name:/^Kundapur — Udupi/}).click();await expect(page.getByRole('heading',{name:'Kundapur, Udupi',exact:true})).toBeVisible();await expect(page.getByRole('heading',{name:'27 °C'})).toBeVisible();expect(requests).toEqual(['?latitude=13.6250993&longitude=74.6915722']);await locate(page,14,75);expect(requests).toHaveLength(1)
})
test('provider and tile failure keep Home honest while historical evidence remains on Flood Map',async({page})=>{
 await setup(page);await page.route('**/api/weather?**',r=>r.fulfill({status:503,contentType:'application/json',body:JSON.stringify({message:'Controlled provider failure'})}));await page.goto('/');await locate(page);await expect(page.getByRole('alert').filter({hasText:'Controlled provider failure'})).toBeVisible();await expect(page.getByRole('heading',{name:'Current weather unavailable'})).toBeVisible()
 await expect(page.locator('.home-flood-map path[fill="#dc6047"]')).toHaveCount(0);await expect(page.getByText(/Background tiles are unavailable/)).toBeVisible();await expect(page.locator('.home-flood-map img.leaflet-tile')).toHaveCount(0)
 await expect(page.getByRole('button',{name:'Show historical evidence'})).toHaveCount(0)
 await page.getByRole('link',{name:'Full map',exact:true}).click();await expect(page).toHaveURL(/\/flood-map$/);await expect(page.locator('.intelligence-map path[fill="#dc6047"]')).toHaveCount(56)
 await page.getByLabel('Historical evidence cell (keyboard alternative)',{exact:true}).selectOption({index:1});await expect(page.getByRole('heading',{name:'Flood evidence details'})).toBeVisible()
})
test('Home does not request historical evidence or shelters and retains explicit unknown outcomes',async({page})=>{
 await setup(page,'denied');const calls=[];page.on('request',r=>{if(/\/api\/(?:shelters|flood-map\/historical)/.test(r.url()))calls.push(r.url())})
 await page.goto('/');await expect(page.locator('.home-river-line')).toContainText('Reviewed river outlook: unavailable');await expect(page.getByText(/Choose your place to see its official IMD district warning/)).toBeVisible()
 await expect(page.getByText(/reviewed historical cells|Verified Open shelters/)).toHaveCount(0);await expect(page.getByRole('button',{name:'Refresh shelters'})).toHaveCount(0);await expect(page.locator('.home-flood-map path[fill="#dc6047"]')).toHaveCount(0)
 await expect(page.getByText(/Choose your town or use your location to see the riskiest spots/)).toBeVisible();expect(calls).toEqual([])
})
test('Shelters retains its fresh fixture and expiry protection after removal from Home',async({page})=>{
 await setup(page,'denied');let calls=0
 await page.route('**/api/shelters*',async r=>{
  calls++;if(calls>1)return r.fulfill({status:503,contentType:'application/json',body:JSON.stringify({detail:'Controlled directory outage'})})
  const now=await page.evaluate(()=>Date.now());return r.fulfill({status:200,contentType:'application/json',body:JSON.stringify({status:'available',mode:'demonstration',shelters:[{id:'isolated-test',name:'ISOLATED TEST entrance',address:'TEST ONLY',district_id:'nic:udupi.nic.in',district_name:'Udupi',status:'open',capacity:10,occupancy:6,available_capacity:4,latitude:13.4,longitude:74.7,verified_at:new Date(now).toISOString(),updated_at:new Date(now).toISOString(),verification_expires_at:new Date(now+5000).toISOString(),demonstration:true,revision:1}]})})
 });await page.goto('/');expect(calls).toBe(0);await nav(page).getByRole('link',{name:'Shelters',exact:true}).click();await expect(page.getByText('ISOLATED TEST entrance',{exact:true})).toBeVisible();expect(calls).toBe(1)
 await page.clock.fastForward(5001);await expect(page.getByRole('alert').filter({hasText:'Controlled directory outage'})).toBeVisible();await expect(page.getByText('ISOLATED TEST entrance',{exact:true})).toHaveCount(0);expect(calls).toBe(2)
})
test('Home has a large 60 percent map on desktop and normal overflow-free mobile scrolling',async({page})=>{
 await setup(page,'denied')
 for(const size of [{width:1366,height:768},{width:1920,height:1080},{width:1600,height:900},{width:390,height:844},{width:320,height:720}]){
  await page.setViewportSize(size);await page.goto('/');await expect(page.getByRole('region',{name:'Karnataka emergency map'})).toBeVisible();const left=await page.locator('.home-area-summary').boundingBox(),stage=await page.locator('.home-map-stage').boundingBox(),map=await page.locator('.home-flood-map').boundingBox()
  expect(map.height).toBeGreaterThan(350);expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true)
  if(size.width>1000){await expect(page.locator('.home-viewport-fit')).toBeVisible();expect(await page.evaluate(()=>document.documentElement.scrollHeight)).toBe(size.height);expect(stage.x).toBeGreaterThan(left.x+left.width);expect(stage.width/(stage.width+left.width)).toBeCloseTo(.6,1)}else{expect(stage.y).toBeGreaterThan(left.y+left.height-1);await page.locator('.home-flood-map').scrollIntoViewIfNeeded();await expect(page.locator('.home-flood-map')).toBeVisible()}
 }
})

test('reload makes one fresh bounded GPS attempt and stores no location coordinates',async({page})=>{
 await setup(page,'denied');await page.goto('/');await expect(page.getByText(/Location permission was denied/)).toBeVisible();expect(await page.evaluate(()=>window.__gpsCalls)).toBe(1);await page.reload();await expect(page.getByRole('heading',{name:'Karnataka statewide view'})).toBeVisible();await expect(page.getByText(/Location permission was denied/)).toBeVisible();expect(await page.evaluate(()=>window.__gpsCalls)).toBe(1);expect(await page.evaluate(()=>Object.entries(sessionStorage))).toEqual([['floodpulse-home-location-attempted','1']])
})

test('native browser geolocation permission grant automatically selects the controlled GPS fix',async({page})=>{
 const requests=await setup(page,'native');await page.context().grantPermissions(['geolocation']);await page.context().setGeolocation({latitude:13.34221,longitude:74.74804,accuracy:40});await page.goto('/');await expect(page.getByRole('heading',{name:'GPS-selected point',exact:true})).toBeVisible();await expect(page.getByRole('heading',{name:'27 °C',exact:true})).toBeVisible();expect(requests).toEqual(['?latitude=13.34221&longitude=74.74804']);await expect(page.getByText(/Browser-reported accuracy: ±40 m/)).toBeVisible();await expect(page.locator('.home-flood-map path[fill="#286ba4"]')).toHaveCount(2)
})
