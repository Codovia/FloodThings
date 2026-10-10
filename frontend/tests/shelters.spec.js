import {selectPoint} from './pointSelection.js'
import {expect,test} from '@playwright/test'
const weather=point=>({status:'available',retrieved_at:new Date().toISOString(),location:point,grid_location:point,current:{temperature_c:27,humidity_percent:80,precipitation_mm:0,interval_seconds:900,valid_at:new Date().toISOString()},prediction_status:'not_available',forecast:Array.from({length:7},(_,i)=>({date:`2026-10-${String(9+i).padStart(2,'0')}`,temperature_min_c:22,temperature_max_c:30,precipitation_mm:i,weather_code:61}))})
test.beforeEach(async({page})=>{
 await page.route('**/*',route=>{
  const u=new URL(route.request().url());if(!['127.0.0.1','localhost'].includes(u.hostname))return route.abort()
  if(u.pathname==='/api/weather')return route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(weather({latitude:+u.searchParams.get('latitude'),longitude:+u.searchParams.get('longitude')}))})
  return route.continue()
 })
})

test('actual PostgreSQL public directory is empty, read-only and leaves weather/manual workflows usable',async({page})=>{
 await page.goto('/');await expect(page.getByRole('list',{name:'Daily weather forecasts'}).getByRole('article')).toHaveCount(7)
 await expect(page.getByRole('button',{name:'Refresh shelters'})).toBeEnabled();await page.getByRole('button',{name:'Refresh shelters'}).click()
 await expect(page.getByText('No currently verified open shelters are available in this directory.')).toBeVisible()
 const response=await page.request.post('/api/shelters',{data:{name:'Must not write'}});expect(response.status()).toBe(405)
 const unauthorized=await page.request.post('/api/admin/shelters',{data:{name:'TEST ONLY',address:'Not a shelter',district_id:'nic:udupi.nic.in',capacity:10,occupancy:0}});expect(unauthorized.status()).toBe(401)
 await page.getByText('Change location',{exact:true}).click();await selectPoint(page,13.6,74.8)
 await expect(page.getByRole('heading',{name:'GPS-selected point'})).toBeVisible()
 await expect(page.getByRole('list',{name:'Daily weather forecasts'}).getByRole('article')).toHaveCount(7)
 await expect(page.getByText(/Flood prediction is not available/)).toBeVisible()
})

test('explicit demonstration fixtures render exact entrance, mobile map and no unsafe replacement after failure',async({page})=>{
 const stamp=new Date().toISOString();const data={status:'available',mode:'demonstration',total:1,verification_valid_hours:24,shelters:[{id:'isolated-fixture',name:'DEMONSTRATION ONLY — not a shelter',address:'Isolated fixture',district_name:'Udupi',latitude:13.5,longitude:74.7,capacity:10,occupancy:2,available_capacity:8,water:'yes',toilets:'unknown',accessibility:'TEST ONLY',status:'open',verified_at:stamp,updated_at:stamp,verification_expires_at:new Date(Date.now()+86400000).toISOString(),demonstration:true,straight_line_km:12,restrictions:'DO NOT TRAVEL',contact:null}]}
 await page.route('**/api/shelters?**',r=>r.fulfill({status:200,contentType:'application/json',body:JSON.stringify(data)}))
 await page.setViewportSize({width:390,height:844});await page.goto('/');await expect(page.getByRole('button',{name:'Refresh shelters'})).toBeEnabled();await page.getByRole('button',{name:'Refresh shelters'}).click()
 await expect(page.getByText(/DEMONSTRATION ONLY — isolated test assignments/)).toBeVisible();await expect(page.getByRole('region',{name:'Verified open shelter entrances'})).toBeVisible()
 const link=page.getByRole('link',{name:'Inspect demonstration directions (not for travel)'});const url=new URL(await link.getAttribute('href'));expect(url.searchParams.get('destination')).toBe('13.5,74.7');expect(url.searchParams.get('api')).toBe('1')
 await expect(page.getByText(/not verified flood-safe/)).toBeVisible();expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true)
 await page.route('**/api/shelters?**',r=>r.fulfill({status:503,contentType:'application/json',body:JSON.stringify({detail:'Controlled shelter database outage'})}))
 await page.getByRole('button',{name:'Refresh shelters'}).click();await expect(page.getByText(/Controlled shelter database outage/)).toBeVisible();await expect(link).toHaveCount(0)
})

test('separate admin area has no public registration and rejects an invalid login',async({page})=>{
 await page.goto('/admin');await expect(page.getByRole('heading',{name:'Shelter administrator',exact:true})).toBeVisible();await expect(page.getByRole('button',{name:'Sign in'})).toBeVisible()
 expect(await page.getByRole('button',{name:/register/i}).count()).toBe(0)
 await page.getByLabel('Username',{exact:true}).fill('not-an-admin');await page.getByLabel('Password',{exact:true}).fill('WRONG ISOLATED TEST PASSWORD')
 await page.getByRole('button',{name:'Sign in'}).click();await expect(page.getByText('Invalid administrator credentials')).toBeVisible();await expect(page.getByLabel('Password',{exact:true})).toHaveValue('')
 await page.getByRole('link',{name:'Return to citizen dashboard'}).click();await expect(page.getByRole('heading',{name:'FloodPulse',exact:true})).toBeVisible()
})

test('isolated authenticated admin form uses the real district contract and requires renewed confirmations',async({page})=>{
 // Browser fixtures are explicitly demonstration-only; no production write occurs.
 let authenticated=false,record=null;const stamp=new Date().toISOString()
 await page.route('**/api/admin/**',async route=>{
  const request=route.request(),path=new URL(request.url()).pathname,method=request.method();let status=200,data={}
  if(path==='/api/admin/login'){
   expect(request.headers()['x-floodpulse-login']).toBe('1');authenticated=true
   data={user:{id:'isolated-admin',username:'isolated-admin'},csrf_token:'ISOLATED_CSRF',mode:'demonstration'}
  }else if(!authenticated){status=401;data={detail:'Administrator login required'}}
  else if(path==='/api/admin/logout'){expect(request.headers()['x-csrf-token']).toBe('ISOLATED_CSRF');authenticated=false;data={status:'logged_out'}}
  else if(method==='GET'){data={shelters:record?[record]:[],total:record?1:0}}
  else{
   expect(request.headers()['x-csrf-token']).toBe('ISOLATED_CSRF');const body=request.postDataJSON()
   expect(body.district_id).toBe('nic:udupi.nic.in')
   if(method==='POST'){expect(body.status).toBe('pending');expect(body.verification.authorization).toBe(false);status=201}
   else{expect(body.status).toBe('open');for(const key of ['authorization','entrance','usability','capacity'])expect(body.verification[key]).toBe(true)}
   record={...body,id:'b45b49ac-ade4-4e37-9228-11bf8cfd125e',district_name:'Udupi',revision:record?2:1,updated_at:stamp,verified_at:body.status==='open'?stamp:null,publicly_available:body.status==='open',demonstration:true};data=record
  }
  await route.fulfill({status,contentType:'application/json',body:JSON.stringify(data)})
 })
 await page.setViewportSize({width:390,height:844});await page.goto('/admin')
 await page.getByLabel('Username',{exact:true}).fill('isolated-admin');await page.getByLabel('Password',{exact:true}).fill('ISOLATED TEST PASSWORD');await page.getByRole('button',{name:'Sign in'}).click()
 await expect(page.getByText(/DEMONSTRATION ONLY — isolated database/)).toBeVisible()
 await expect(page.getByRole('option',{name:'Satellite imagery',exact:true})).toBeDisabled();await expect(page.getByRole('option',{name:'Satellite Hybrid',exact:true})).toBeDisabled();await expect(page.getByLabel('Search place or building name')).toBeDisabled()
 await page.getByRole('button',{name:'Search districts and localities'}).click();await page.getByLabel('Karnataka district').selectOption('nic:udupi.nic.in');await page.getByRole('list',{name:'District localities'}).getByRole('button',{name:/^Udupi —/}).click();await expect(page.getByLabel('Entrance latitude',{exact:true})).toHaveValue('');await expect(page.getByLabel('Entrance longitude',{exact:true})).toHaveValue('');await expect(page.getByText(/This point is not a verified entrance/)).toBeVisible()
 await page.getByRole('region',{name:'Administrator entrance selection map'}).click({position:{x:110,y:140}});await expect(page.getByLabel('Entrance latitude',{exact:true})).not.toHaveValue('');await expect(page.getByLabel('Entrance longitude',{exact:true})).not.toHaveValue('');await expect(page.getByRole('checkbox',{name:'This exact entrance has been independently verified'})).not.toBeChecked()
 await page.getByLabel('Facility name',{exact:true}).fill('DEMONSTRATION ONLY — fixture')
 await page.getByLabel('Facility address',{exact:true}).fill('Not an actual emergency shelter')
 await page.getByLabel('Shelter district',{exact:true}).selectOption('nic:udupi.nic.in')
 await page.getByLabel('Maximum capacity',{exact:true}).fill('10');await page.getByLabel('Current occupancy',{exact:true}).fill('2')
 await expect(page.getByLabel('Shelter status',{exact:true})).toBeDisabled()
 await page.getByRole('button',{name:'Save shelter assignment'}).click();await expect(page.getByText(/Assignment saved/)).toBeVisible()
 await page.getByLabel('Entrance latitude',{exact:true}).fill('13.5');await page.getByLabel('Entrance longitude',{exact:true}).fill('74.7')
 await page.getByLabel('Shelter status',{exact:true}).selectOption('open')
 for(const label of ['Facility is authorized for shelter use','This exact entrance has been independently verified','Facility is currently usable','Capacity and current occupancy have been checked'])await page.getByLabel(label,{exact:true}).check()
 await page.getByLabel('Verification evidence and method',{exact:true}).fill('Isolated test confirmations only')
 const saved=page.waitForResponse(r=>r.request().method()==='PUT');await page.getByRole('button',{name:'Save shelter assignment'}).click();await saved
 await expect(page.getByLabel('Facility is authorized for shelter use',{exact:true})).not.toBeChecked()
 await expect(page.getByLabel('Shelter status',{exact:true})).toHaveValue('open')
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true)
 for(const size of [{width:1366,height:768},{width:1920,height:1080},{width:390,height:844}]){await page.setViewportSize(size);await page.getByRole('heading',{name:'Inspect facility & select entrance'}).scrollIntoViewIfNeeded();expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);await page.screenshot({path:`../data/recovery/fullscreen_ui_v1/after/admin-isolated-${size.width}.png`,fullPage:true})}
 await page.getByRole('button',{name:'Sign out'}).click();await expect(page.getByRole('button',{name:'Sign in'})).toBeVisible()
})
