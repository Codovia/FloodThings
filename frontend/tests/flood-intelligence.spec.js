import { openTab } from './oneScreen.js'
import {test,expect} from '@playwright/test'
import {emptyShelterDirectory} from './shelterFixture.js'
import {readFileSync} from 'node:fs'
const source=new URL('../../data/processed/udupi_flood_spatial_v1/',import.meta.url)
test.beforeEach(async({page})=>{await page.route('**/*',route=>{const u=new URL(route.request().url());if(!['127.0.0.1','localhost'].includes(u.hostname))return route.abort();if(u.pathname==='/api/weather')return route.fulfill({status:503,contentType:'application/json',body:JSON.stringify({message:'Weather intentionally isolated in map test'})});return route.continue()});await emptyShelterDirectory(page)})
test('31 districts, original GeoJSON, independent layers, details and statewide reset',async({page})=>{
 const errors=[];page.on('pageerror',e=>errors.push(e.message));await page.goto('/flood-map')
 const select=page.getByLabel('Go to district',{exact:true});await expect(select.locator('option')).toHaveCount(32)
 await expect(page.locator('.intelligence-map path[fill="#dc6047"]')).toHaveCount(56)
 const response=await page.request.get('/api/flood-map/historical');expect(response.ok()).toBe(true);const body=await response.json()
 for(const id of [2728,3551]){const saved=JSON.parse(readFileSync(new URL(`event_${id}.geojson`,source),'utf8'));expect(body.geojson.features.filter(f=>f.properties.event_id===id).map(f=>f.geometry)).toEqual(saved.features.map(f=>f.geometry))}
 await select.selectOption('nic:udupi.nic.in');await expect(page.locator('.intelligence-map path[fill="#dc6047"]')).toHaveCount(56)
 await page.getByRole('button',{name:'Zoom to past floods',exact:true}).click()
 await page.locator('.intelligence-map path[fill="#dc6047"]').first().click({force:true});await expect(page.getByRole('heading',{name:'Flood evidence details'})).toBeVisible();await expect(page.getByText(/Maximum water seen by satellite during this flood/)).toBeVisible();await expect(page.getByText(/SHA-256|Stable feature ID/)).toHaveCount(0)
 await page.getByRole('button',{name:'Close',exact:true}).click();await expect(page.getByRole('heading',{name:'Flood evidence details'})).toHaveCount(0)
 await expect(page.getByLabel(/Flood-Prone/i)).toHaveCount(0);await openTab(page,'Sources');await expect(page.getByText(/No verified potential flood-prone zone dataset/)).toBeVisible();await expect(page.locator('.intelligence-map path[fill="#dc6047"]')).toHaveCount(56)
 await select.selectOption('nic:kolar.nic.in');await openTab(page,'Past floods');await expect(page.getByText(/No past floods are mapped for this district/)).toBeVisible();await expect(page.getByText(/Map bounds are unavailable for Kolar/)).toBeVisible();await expect(page.locator('.intelligence-map path[fill="#dc6047"]')).toHaveCount(0)
 await page.getByRole('button',{name:'Show all Karnataka'}).click();await expect(page.locator('.intelligence-map path[fill="#dc6047"]')).toHaveCount(56);await expect(page.getByLabel('Past floods (satellite)')).toBeChecked()
 await page.getByLabel('Verified shelters',{exact:true}).check();await openTab(page,'Past floods');await expect(page.getByText('No currently verified open shelters are available in this directory.')).toBeVisible();expect(errors).toEqual([])
})
test('mobile cell details, no drains research layer and map layer cleanup',async({page})=>{
 await page.setViewportSize({width:390,height:844});await page.goto('/flood-map');const districts=page.getByLabel('Go to district',{exact:true});await expect(districts.locator('option')).toHaveCount(32);await districts.focus();await districts.selectOption('nic:udupi.nic.in')
 await expect(page.getByLabel('Drains (Udupi study)')).toHaveCount(0);await expect(page.getByLabel('Mapped flood cell')).toHaveCount(0)
 await page.getByRole('button',{name:'Zoom to past floods',exact:true}).click();await page.locator('.intelligence-map path[fill="#dc6047"]').first().click({force:true});await expect(page.getByRole('heading',{name:'Flood evidence details'})).toBeVisible();await page.getByRole('button',{name:'Close',exact:true}).click();await page.getByRole('button',{name:'Layers & legend'}).click();await page.getByLabel('Past floods (satellite)',{exact:true}).uncheck();await page.getByRole('button',{name:'Close',exact:true}).click();await expect(page.locator('.intelligence-map path[fill="#dc6047"]')).toHaveCount(0);await expect(page.getByRole('heading',{name:'Flood evidence details'})).toHaveCount(0);expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true)
})
test('unavailable historical geometry clears map and cannot become a negative or hazard',async({page})=>{
 await page.route('**/api/flood-map/historical*',r=>r.fulfill({status:503,contentType:'application/json',body:JSON.stringify({detail:'Controlled historical geometry failure'})}));await page.goto('/flood-map');await expect(page.getByRole('alert').filter({hasText:'Controlled historical geometry failure'})).toBeVisible();await expect(page.locator('.intelligence-map path[fill="#dc6047"]')).toHaveCount(0);await expect(page.getByLabel('Mapped flood cell')).toHaveCount(0);await openTab(page,'Sources');await expect(page.getByText(/No verified potential flood-prone/)).toBeVisible();await openTab(page,'Past floods');await expect(page.getByText('Past floods could not be loaded.')).toBeVisible();await expect(page.getByRole('button',{name:'Retry map evidence'})).toBeVisible()
})
// TEST FIXTURE ONLY: /api/river-forecast shape with invented values; live GloFAS is not called by this test.
const riverPoint=(id,river,place,level,share2,share5,lat,lon)=>({id,river,place,district:'Fixture',grid:{latitude:lat,longitude:lon},level,meaning:'TEST',members:50,
 peak:{date:'2026-10-25',median_m3s:100,max_m3s:200,share_above:{'2_year':share2,'5_year':share5,'10_year':0}},days:[],flood_levels_m3s:{'2_year':100,'5_year':200,'10_year':300},
 ai_model:level==='severe'?{status:'available',flood_likely:true,first_flagged_date:'2026-10-26',peak_upstream_rain_3d_mm:212,evaluation:{model_f1:.71,rain_rule_f1:.62,documented_floods_flagged:['2019-08-08']}}
  :{status:'not_used',message:'AI model not used here: a simple rain rule did better in the test years (2016–2021).',evaluation:{model_f1:.51,rain_rule_f1:.58,documented_floods_flagged:[]}}})
test('Rivers tab shows the checked river forecast as issued, one screen, and an outage never reads as normal',async({page})=>{
 const { expectOneScreen } = await import('./oneScreen.js')
 let available=true
 await page.route('**/api/river-forecast',route=>route.fulfill(available?{status:200,contentType:'application/json',body:JSON.stringify({status:'available',label:'TEST',points:[
  riverPoint('t1','Testriver','Fixturepur','severe',.9,.6,16.625,74.875),riverPoint('t2','Calmriver','Quietpur','low',0,0,12.875,74.925)]})}
  :{status:503,contentType:'application/json',body:JSON.stringify({status:'unavailable',points:[],message:'River forecast provider unavailable (timeout).'})}))
 for(const size of [{width:1366,height:768},{width:390,height:844}]){
  await page.setViewportSize(size);await page.goto('/flood-map');await openTab(page,'Rivers')
  const list=page.getByRole('list',{name:'River flood forecast, next 7 days'})
  await expect(list.getByRole('listitem')).toHaveCount(2)
  await expect(list.getByRole('listitem').first()).toContainText(/Severe.*Testriver.*Fixturepur.*90% of runs above 2-year flood level · 60% above 5-year/)
  await expect(page.getByText(/Not observed water levels or an official warning/)).toBeVisible()
  await expect(list.getByRole('listitem').first()).toContainText(/AI: flood likely within 3 days/)
  await expect(list.getByRole('listitem').nth(1)).toContainText(/AI: not used here/)
  await page.waitForTimeout(1600);expect(await expectOneScreen(page),`${size.width}`).toEqual({page:0,width:0,scrolls:0,outside:0})
 }
 await page.setViewportSize({width:1366,height:768});await page.goto('/flood-map')
 await expect(page.locator('.intelligence-map path[fill="#b71c1c"][stroke="#0d3b66"]')).toHaveCount(1)  // the severe river marker
 await openTab(page,'Rivers');await page.getByRole('button',{name:'How the river forecast was checked'}).click()
 await expect(page.getByRole('dialog')).toContainText(/Bhima at Afzalpur and Kaveri at Srirangapatna did not pass/);await page.getByRole('button',{name:'Close',exact:true}).click()
 available=false;await page.reload();await openTab(page,'Rivers')
 await expect(page.getByText(/River forecast unavailable \(River forecast provider unavailable \(timeout\)\.\)\. This does not mean rivers are normal/)).toBeVisible()
 await expect(page.getByRole('list',{name:'River flood forecast, next 7 days'})).toHaveCount(0)
})
