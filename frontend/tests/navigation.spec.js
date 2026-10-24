import { openTab, expectOneScreen } from './oneScreen.js'
import {selectPoint} from './pointSelection.js'
import {test,expect} from '@playwright/test'
import {emptyShelterDirectory} from './shelterFixture.js'
const stamp='2026-10-10T06:00:00Z'
async function setup(page){
 let requests=0
 await page.clock.install({time:new Date(stamp)});await page.clock.pauseAt(new Date(stamp))
 await page.route('**/*',async route=>{
  const u=new URL(route.request().url());if(!['127.0.0.1','localhost'].includes(u.hostname))return route.abort()
  if(u.pathname==='/api/weather'){
   requests++;const location={latitude:+(u.searchParams.get('latitude')||12.9767936),longitude:+(u.searchParams.get('longitude')||77.590082)}
   return route.fulfill({status:200,contentType:'application/json',body:JSON.stringify({status:'available',location,retrieved_at:await page.evaluate(()=>new Date().toISOString()),current:{temperature_c:27,humidity_percent:80,precipitation_mm:0,valid_at:stamp,interval_seconds:900},grid_location:location,forecast:Array.from({length:7},(_,i)=>({date:`2026-10-${10+i}`,temperature_min_c:22,temperature_max_c:29,precipitation_mm:i,weather_code:61}))})})
  }
  return route.continue()
 })
 await emptyShelterDirectory(page)
 return ()=>requests
}
const nav=page=>page.getByRole('navigation',{name:'Main navigation'})

test('five routes, direct URLs, back/forward, persistent location and one freshness lifecycle',async({page})=>{
 const requests=await setup(page);await page.goto('/weather');await expect(page.getByText('27 °C',{exact:true})).toBeVisible()
 await selectPoint(page,13.34,74.74);await expect(page.getByRole('heading',{name:'GPS-selected point'})).toBeVisible();await expect.poll(requests).toBe(2)
 // The page clock is frozen while the browser stamps GPS fixes with real time, so the fix looks stale and Shelters
 // would refresh it automatically. Location access is withdrawn so this test checks only that the point persists.
 await page.context().clearPermissions()
 await nav(page).getByRole('link',{name:'Flood Map',exact:true}).click();await openTab(page,'Past floods');await expect(page.getByText(/56 mapped flood cells/)).toBeVisible();await expect(page.locator('.historical-map path[fill="#dc6047"]')).toHaveCount(56)
 await nav(page).getByRole('link',{name:'Shelters',exact:true}).click();await expect(page.getByText('No currently verified open shelters are available in this directory.')).toBeVisible()
 await page.goBack();await expect(page).toHaveURL(/\/flood-map$/);await expect(page.locator('.historical-map path[fill="#dc6047"]')).toHaveCount(56)
 await page.goForward();await expect(page).toHaveURL(/\/shelters$/)
 await nav(page).getByRole('link',{name:'Home',exact:true}).click();await expect(page.getByRole('region',{name:'Karnataka emergency map'})).toBeVisible();await expect(page.getByRole('heading',{name:'GPS-selected point'})).toBeVisible();await expect.poll(requests).toBe(2)
 await page.clock.fastForward(6*3600000);await expect.poll(requests).toBe(3)
 await page.evaluate(()=>{history.pushState(null,'','/weather');dispatchEvent(new PopStateEvent('popstate'))});await openTab(page,'7 days');await expect(page.getByRole('list',{name:'Daily weather forecasts'}).getByRole('article')).toHaveCount(7);expect(requests()).toBe(3)
 await nav(page).getByRole('link',{name:'Admin',exact:true}).click();await expect(page.getByRole('button',{name:'Sign in'})).toBeVisible();await expect(nav(page).getByRole('link',{name:'Admin',exact:true})).toHaveAttribute('aria-current','page')
 for(const [url,title] of [['/','FloodPulse'],['/weather','Weather details'],['/flood-map','Flood Map'],['/shelters','Emergency Shelters'],['/admin','Administration']]){
  await page.goto(url);await expect(page.getByRole('heading',{name:title,exact:true,level:1})).toBeVisible()
 }
})

test('mobile menu, keyboard, layer toggles and maps remain usable after routing',async({page})=>{
 await setup(page);await page.setViewportSize({width:390,height:844});await page.goto('/')
 await expect(nav(page)).not.toBeVisible();const menu=page.getByRole('button',{name:'Open navigation menu'});await menu.focus();await page.keyboard.press('Enter');await expect(nav(page)).toBeVisible();await page.keyboard.press('Escape');await expect(menu).toBeFocused()
 await menu.click();await nav(page).getByRole('link',{name:'Flood Map',exact:true}).click();await expect(nav(page)).not.toBeVisible();await expect(page.getByRole('heading',{name:'Flood Map',exact:true})).toBeFocused()
 await expect(page.locator('.historical-map path[fill="#dc6047"]')).toHaveCount(56)
 // Phones: layer switches are in the "Layers & legend" popup.
 await page.getByRole('button',{name:'Layers & legend'}).click();await page.getByLabel('Past floods (satellite)', {exact:true}).uncheck();await expect(page.locator('.historical-map path[fill="#dc6047"]')).toHaveCount(0);await page.getByLabel('Past floods (satellite)', {exact:true}).check();await page.getByRole('button',{name:'Close',exact:true}).click();await expect(page.locator('.historical-map path[fill="#dc6047"]')).toHaveCount(56)
 await expect(page.getByLabel('Drains (Udupi study)')).toHaveCount(0)
 for(const url of ['/','/weather','/flood-map','/shelters','/report','/alerts','/how-it-works','/admin']){await page.goto(url);await expect(page.getByRole('heading',{level:1})).toBeAttached();await page.waitForTimeout(800);expect(await expectOneScreen(page),url).toEqual({page:0,width:0,scrolls:0,outside:0})}
})

test('missing data, unknown routes and shelter errors do not invent readings or destinations',async({page})=>{
 await setup(page);await page.route('**/api/weather*',r=>r.fulfill({status:503,contentType:'application/json',body:JSON.stringify({message:'Controlled weather outage'})}));await page.route('**/api/shelters*',r=>r.fulfill({status:503,contentType:'application/json',body:JSON.stringify({detail:'Controlled directory outage'})}))
 await page.goto('/weather');await expect(page.getByText(/Controlled weather outage/)).toBeVisible();await expect(page.getByRole('list',{name:'Daily weather forecasts'})).toHaveCount(0)
 await nav(page).getByRole('link',{name:'Shelters',exact:true}).click();await expect(page.getByText(/Controlled directory outage/)).toBeVisible();await expect(page.getByRole('link',{name:'Open external entrance directions'})).toHaveCount(0)
 await page.goto('/missing');await expect(page.getByRole('heading',{name:'This page is unavailable'})).toBeVisible();await page.getByRole('link',{name:'Return Home'}).click();await expect(page).toHaveURL(/\/$/)
})
