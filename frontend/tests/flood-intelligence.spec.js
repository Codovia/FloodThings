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
