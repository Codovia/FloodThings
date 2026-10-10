import {test,expect} from '@playwright/test'
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
 return ()=>requests
}
const nav=page=>page.getByRole('navigation',{name:'Main navigation'})

test('five routes, direct URLs, back/forward, persistent location and one freshness lifecycle',async({page})=>{
 const requests=await setup(page);await page.goto('/weather'); await page.getByText('Change location',{exact:true}).click();await expect(page.getByText('27 °C',{exact:true})).toBeVisible()
 await page.getByLabel('Weather latitude').fill('13.34');await page.getByLabel('Weather longitude').fill('74.74');await page.getByRole('button',{name:'Get point weather'}).click();await expect(page.getByRole('heading',{name:'Entered coordinates'})).toBeVisible();expect(requests()).toBe(2)
 await nav(page).getByRole('link',{name:'Flood Map',exact:true}).click();await expect(page.getByText(/56 eligible historical cells/)).toBeVisible();await expect(page.locator('.historical-map path[fill="#dc6047"]')).toHaveCount(56)
 await nav(page).getByRole('link',{name:'Shelters',exact:true}).click();await expect(page.getByText('No currently verified open shelters are available in this directory.')).toBeVisible()
 await page.goBack();await expect(page).toHaveURL(/\/flood-map$/);await expect(page.locator('.historical-map path[fill="#dc6047"]')).toHaveCount(56)
 await page.goForward();await expect(page).toHaveURL(/\/shelters$/)
 await nav(page).getByRole('link',{name:'Home',exact:true}).click();await expect(page.getByRole('region',{name:'Weather location selection map'})).toBeVisible();await expect(page.getByRole('heading',{name:'Entered coordinates'})).toBeVisible();expect(requests()).toBe(2)
 await page.clock.fastForward(6*3600000);await expect.poll(requests).toBe(3)
 await nav(page).getByRole('link',{name:'Weather & AI',exact:true}).click();await expect(page.getByRole('list',{name:'Daily weather forecasts'}).getByRole('article')).toHaveCount(7);expect(requests()).toBe(3)
 await nav(page).getByRole('link',{name:'Admin',exact:true}).click();await expect(page.getByRole('button',{name:'Sign in'})).toBeVisible();await expect(nav(page).getByRole('link',{name:'Admin',exact:true})).toHaveAttribute('aria-current','page')
 for(const [url,title] of [['/','FloodPulse'],['/weather','Weather & AI'],['/flood-map','Flood Map'],['/shelters','Emergency Shelters'],['/admin','Administration']]){
  await page.goto(url);await expect(page.getByRole('heading',{name:title,exact:true,level:1})).toBeVisible()
 }
})

test('mobile menu, keyboard, layer toggles and maps remain usable after routing',async({page})=>{
 await setup(page);await page.setViewportSize({width:390,height:844});await page.goto('/')
 await expect(nav(page)).not.toBeVisible();const menu=page.getByRole('button',{name:'Open navigation menu'});await menu.focus();await page.keyboard.press('Enter');await expect(nav(page)).toBeVisible();await page.keyboard.press('Escape');await expect(menu).toBeFocused()
 await menu.click();await nav(page).getByRole('link',{name:'Flood Map',exact:true}).click();await expect(nav(page)).not.toBeVisible();await expect(page.getByRole('heading',{name:'Flood Map',exact:true})).toBeFocused()
 await expect(page.locator('.historical-map path[fill="#dc6047"]')).toHaveCount(56);await page.getByLabel('Historical Flood Locations', {exact:true}).uncheck();await expect(page.locator('.historical-map path[fill="#dc6047"]')).toHaveCount(0);await page.getByLabel('Historical Flood Locations', {exact:true}).check();await expect(page.locator('.historical-map path[fill="#dc6047"]')).toHaveCount(56)
 await page.getByLabel('Drainage / waterways',{exact:true}).check();await page.getByRole('button',{name:'Show research layers'}).click();await expect(page.getByRole('region',{name:'Udupi drainage research geography'})).toBeVisible()
 for(const url of ['/','/weather','/flood-map','/shelters','/admin']){await page.goto(url);await expect(page.getByRole('heading',{level:1})).toBeVisible();expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true)}
})

test('missing data, unknown routes and shelter errors do not invent readings or destinations',async({page})=>{
 await setup(page);await page.route('**/api/weather*',r=>r.fulfill({status:503,contentType:'application/json',body:JSON.stringify({message:'Controlled weather outage'})}));await page.route('**/api/shelters*',r=>r.fulfill({status:503,contentType:'application/json',body:JSON.stringify({detail:'Controlled directory outage'})}))
 await page.goto('/weather'); await page.getByText('Change location',{exact:true}).click();await expect(page.getByText(/Controlled weather outage/)).toBeVisible();await expect(page.getByRole('list',{name:'Daily weather forecasts'})).toHaveCount(0)
 await nav(page).getByRole('link',{name:'Shelters',exact:true}).click();await expect(page.getByText(/Controlled directory outage/)).toBeVisible();await expect(page.getByRole('link',{name:'Open external entrance directions'})).toHaveCount(0)
 await page.goto('/missing');await expect(page.getByRole('heading',{name:'This page is unavailable'})).toBeVisible();await page.getByRole('link',{name:'Return Home'}).click();await expect(page).toHaveURL(/\/$/)
})
