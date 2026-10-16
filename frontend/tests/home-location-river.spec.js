import {test,expect} from '@playwright/test'
// Every named GPS/river success below is an isolated fixture, not an actual review.
async function setup(page,{accuracy=40,delayName=false,river='unsupported'}={}){
 const calls={weather:[],names:0,rivers:0};let release
 await page.clock.install({time:new Date('2026-10-13T11:00:00Z')})
 await page.addInitScript(accuracy=>Object.defineProperty(navigator,'geolocation',{value:{getCurrentPosition:(yes,_,options)=>{window.__gpsOptions=options;yes({coords:{latitude:13.4,longitude:74.7,accuracy},timestamp:Date.now()})}}}),accuracy)
 await page.route('**/*',async route=>{
  const u=new URL(route.request().url())
  if(!['localhost','127.0.0.1'].includes(u.hostname))return route.abort()
  if(u.pathname==='/api/location/provider')return route.fulfill({json:{provider:'MapTiler'}})
  if(u.pathname==='/api/location/reverse'){
   calls.names++;if(delayName)await new Promise(r=>{release=r})
   return route.fulfill({status:200,contentType:'application/json',body:JSON.stringify({status:'available',name:'TEST ONLY GPS town, TEST ONLY context',source:{provider:'MapTiler'},accuracy_supported:true,geometry_verification:'provider_locality_polygon_covers_accuracy'})})
  }
  if(u.pathname==='/api/weather'){
   calls.weather.push(u.search);const point={latitude:+u.searchParams.get('latitude'),longitude:+u.searchParams.get('longitude')}
   return route.fulfill({status:200,contentType:'application/json',body:JSON.stringify({status:'available',location:point,grid_location:point,retrieved_at:'2026-10-13T11:00:00Z',current:{valid_at:'2026-10-13T11:00:00Z',temperature_c:27},forecast:[]})})
  }
  if(u.pathname==='/api/river-outlook'){
   calls.rivers++;const p=route.request().postDataJSON()
   const body=river==='unsupported'?{status:'unsupported',message:'No approved association'}:{status:'partial',requested_model:'forecast_v4',source:{data_kind:'external_modelled_river_forecast'},units:'m³/s',timezone:'GMT',retrieved_at:'2026-10-13T11:00:00Z',fresh_until:'2026-10-13T12:00:00Z',viewing_point:p,grid_location:{latitude:13.4,longitude:74.7},reach:{name:'TEST ONLY river',verified_grid:river!=='ambiguous',expected_grid:{latitude:13.4,longitude:74.7},coverage_description:'TEST ONLY scope'},forecast:Array.from({length:7},(_,i)=>({date:`2026-10-${13+i}`,river_discharge:i===2?null:10+i,river_discharge_mean:null,river_discharge_p25:8+i,river_discharge_p75:20+i}))}
   return route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(body)})
  }
  return route.continue()
 });return {calls,release:()=>release?.()}
}
test('accepted precise GPS gets a verified fixture name without snapping or duplicate weather calls',async({page})=>{
 const {calls}=await setup(page);await page.goto('/');await expect(page.getByRole('heading',{name:'TEST ONLY GPS town, TEST ONLY context',exact:true})).toBeVisible();await expect(page.getByRole('heading',{name:'27 °C',exact:true})).toBeVisible()
 expect(calls.weather).toEqual(['?latitude=13.4&longitude=74.7']);expect(calls.names).toBe(1);expect(calls.rivers).toBe(1);expect(await page.evaluate(()=>window.__gpsOptions)).toEqual({enableHighAccuracy:true,timeout:10000,maximumAge:0})
 await expect(page.locator('.official-summary')).toBeVisible()
})
test('279949-metre GPS accuracy keeps statewide fallback when network provider is unavailable',async({page})=>{
 const {calls}=await setup(page,{accuracy:279949});await page.goto('/');await expect(page.getByRole('heading',{name:'Approximate location — select your town'})).toBeVisible();expect(calls).toEqual({weather:[],names:0,rivers:0});await expect(page.locator('.home-flood-map path[stroke="#286ba4"]')).toHaveCount(0)
 await page.getByRole('button',{name:'Search districts and localities'}).click();await page.getByLabel('Karnataka district',{exact:true}).selectOption('nic:udupi.nic.in');await page.getByRole('button',{name:/^Kundapur — Udupi/}).click();await expect(page.getByRole('heading',{name:'Kundapur, Udupi',exact:true})).toBeVisible();await expect(page.getByRole('heading',{name:'27 °C',exact:true})).toBeVisible();expect(calls.weather).toEqual(['?latitude=13.6250993&longitude=74.6915722'])
})
test('manual town overrides a late geocoding response without altering its weather coordinates',async({page})=>{
 const {calls,release}=await setup(page,{delayName:true});await page.goto('/');await expect(page.getByRole('heading',{name:'GPS-selected point',exact:true})).toBeVisible()
 await page.getByRole('button',{name:'Search districts and localities'}).click();await page.getByLabel('Karnataka district',{exact:true}).selectOption('nic:udupi.nic.in');await page.getByRole('button',{name:/^Kundapur — Udupi/}).click();release();await expect(page.getByRole('heading',{name:'Kundapur, Udupi',exact:true})).toBeVisible();expect(calls.weather.at(-1)).toBe('?latitude=13.6250993&longitude=74.6915722');await expect(page.getByRole('heading',{name:'TEST ONLY GPS town, TEST ONLY context',exact:true})).toHaveCount(0)
})
test('only verified fixture river cells render model discharge, missing values and geographic limitations',async({page})=>{
 await setup(page,{river:'verified'});await page.goto('/');await page.getByText('River forecast table',{exact:true}).click();await expect(page.locator('table.home-river-table')).toBeVisible();await expect(page.getByText('TEST ONLY river',{exact:true})).toBeVisible();await expect(page.locator('table.home-river-table')).toContainText('Unavailable');await expect(page.getByText(/Not observed water level or a warning/)).toBeVisible()
 await expect(page.locator('.home-flood-map path[stroke="#6951a3"]')).toHaveCount(1);await expect(page.getByLabel('Flood and drainage risk')).toBeVisible();await expect(page.locator('.official-summary')).toBeVisible()
 await page.clock.fastForward(3600001);await expect(page.locator('table.home-river-table')).toHaveCount(0);await expect(page.locator('.home-flood-map path[stroke="#6951a3"]')).toHaveCount(0)
})
test('ambiguous river mapping cannot render a model marker, discharge table or warning',async({page})=>{
 await setup(page,{river:'ambiguous'});await page.goto('/');await expect(page.getByText('River outlook could not be checked.')).toBeVisible();await expect(page.locator('table.home-river-table')).toHaveCount(0);await expect(page.locator('.home-flood-map path[stroke="#6951a3"]')).toHaveCount(0);await expect(page.locator('.official-summary')).toBeVisible()
})

test('kilometre-accuracy GPS loads actual selected-point weather and an approximate client town label',async({page})=>{
 const {calls}=await setup(page,{accuracy:1200})
 await page.route('**/api/location/provider',route=>route.fulfill({json:{provider:'BigDataCloud'}}))
 await page.route('https://api.bigdatacloud.net/**',route=>route.fulfill({json:{city:'TEST ONLY approximate town',countryCode:'IN',lookupSource:'coordinates',latitude:13.4,longitude:74.7}}))
 await page.goto('/');await expect(page.getByRole('heading',{name:'TEST ONLY approximate town',exact:true})).toBeVisible()
 await expect(page.getByRole('heading',{name:'27 °C',exact:true})).toBeVisible();expect(calls.weather).toEqual(['?latitude=13.4&longitude=74.7'])
 await expect(page.getByText(/Approximate provider town label/)).toBeVisible()
})
test('coarse GPS can use a clearly marked network estimate for weather but never river context',async({page})=>{
 const {calls}=await setup(page,{accuracy:279949})
 await page.route('https://api.bigdatacloud.net/**',route=>{expect(new URL(route.request().url()).searchParams.has('latitude')).toBe(false);return route.fulfill({json:{city:'TEST ONLY network town',countryCode:'IN',lookupSource:'ipGeolocation',latitude:13.3,longitude:74.6}})})
 await page.goto('/');await expect(page.getByRole('heading',{name:'TEST ONLY network town',exact:true})).toBeVisible()
 await expect(page.getByRole('heading',{name:'27 °C',exact:true})).toBeVisible();expect(calls.weather).toEqual(['?latitude=13.3&longitude=74.6']);expect(calls.rivers).toBe(0)
 await expect(page.getByText(/Approximate network city estimate/)).toBeVisible()
})
