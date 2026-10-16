import { test, expect } from '@playwright/test'
// These layout fixtures are isolated HTTP responses, never observations or DB writes.
test.beforeEach(async({page})=>{
 await page.addInitScript(()=>Object.defineProperty(navigator,'geolocation',{value:{getCurrentPosition:(_yes,no)=>no({code:1})}}))
 await page.route('**/*',route=>{
  const u=new URL(route.request().url())
  if(!['localhost','127.0.0.1'].includes(u.hostname)){
   if(u.hostname==='tile.openstreetmap.org')return route.fulfill({status:200,contentType:'image/png',body:Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aS1cAAAAASUVORK5CYII=','base64')})
   return route.abort()
  }
  if(u.pathname==='/api/shelters')return route.fulfill({status:200,contentType:'application/json',body:JSON.stringify({status:'available',mode:'live',shelters:[],retrieved_at:new Date().toISOString()})})
  return route.continue()
 })
})
async function bounded(locator,viewport){const r=await locator.boundingBox();expect(r).not.toBeNull();expect(r.x).toBeGreaterThanOrEqual(0);expect(r.y).toBeGreaterThanOrEqual(0);expect(r.x+r.width).toBeLessThanOrEqual(viewport.width+1);expect(r.y+r.height).toBeLessThanOrEqual(viewport.height+1);return r}
for(const viewport of [{width:1366,height:768},{width:1920,height:1080},{width:1600,height:900}])test(`Home fits ${viewport.width}x${viewport.height} with internal overflow and fully visible essentials`,async({page})=>{
 await page.setViewportSize(viewport);await page.goto('/');await expect(page.locator('.home-viewport-fit')).toBeVisible()
 expect(await page.evaluate(()=>[innerHeight,document.documentElement.scrollHeight,document.documentElement.scrollWidth])).toEqual([viewport.height,viewport.height,viewport.width])
 for(const selector of ['.app-header','.app-footer','.home-location-bar','.home-summary-cards','.home-area-summary','.home-flood-map','.home-essential-status'])await bounded(page.locator(selector),viewport)
 for(const card of await page.locator('.home-summary-card').all())await bounded(card,viewport)
 const left=await bounded(page.locator('.home-area-summary'),viewport),map=await bounded(page.locator('.home-map-stage'),viewport)
 expect(map.width/(map.width+left.width)).toBeCloseTo(.6,2);expect((await page.locator('.home-flood-map').boundingBox()).height).toBeGreaterThan(350)
 await expect(page.locator('.home-flood-map img.leaflet-tile-loaded').first()).toBeVisible()
 const essential=await page.locator('.home-essential-status').boundingBox(),scroll=page.getByRole('region',{name:'Additional area information'})
 await page.getByText('Data sources, freshness & privacy',{exact:true}).click()
 const needsScroll=await scroll.evaluate(n=>n.scrollHeight>n.clientHeight);if(viewport.height===768)expect(needsScroll).toBe(true)
 await scroll.focus();await page.keyboard.press('End');if(needsScroll)await expect.poll(()=>scroll.evaluate(n=>n.scrollTop)).toBeGreaterThan(0);else expect(await scroll.evaluate(n=>n.scrollTop)).toBe(0)
 expect(await page.evaluate(()=>scrollY)).toBe(0);expect(await page.locator('.home-essential-status').boundingBox()).toEqual(essential)
 await expect(page.getByText('Not connected',{exact:true})).toBeVisible();await bounded(page.getByText('Not connected',{exact:true}),viewport)
 await expect(page.getByRole('button',{name:'Refresh shelters'})).toHaveCount(0);expect(await page.evaluate(()=>scrollY)).toBe(0)
 await expect(page.getByText(/Open-Meteo model output, CC BY 4.0/)).toBeVisible();expect(await page.evaluate(()=>document.documentElement.scrollHeight)).toBe(viewport.height)
 await page.getByText('Map sources & limitations',{exact:true}).focus();await page.keyboard.press('Enter');await expect(page.getByText(/State outline: simplified 2011 context/)).toBeVisible();await bounded(page.locator('.home-map-limitations'),viewport)
})
test('Home keeps keyboard name search accessible without moving the desktop document',async({page})=>{
 await page.setViewportSize({width:1366,height:768});await page.goto('/');await expect(page.locator('.home-viewport-fit')).toBeVisible()
 const search=page.getByRole('button',{name:'Search districts and localities'});await search.focus();await page.keyboard.press('Enter')
 await expect(page.getByLabel('Karnataka district',{exact:true})).toBeVisible();await bounded(page.locator('.directory-content'),{width:1366,height:768});expect(await page.evaluate(()=>document.documentElement.scrollHeight)).toBe(768)
 await page.getByRole('button',{name:'Close place search'}).click();await expect(page.locator('.directory-content')).toHaveCount(0)
})
test('mobile, short screens and enlarged accessibility text keep natural scrolling',async({page})=>{
 for(const viewport of [{width:390,height:844},{width:1366,height:600},{width:1093,height:614}]){
  await page.setViewportSize(viewport);await page.goto('/');await expect(page.locator('.home-viewport-fit')).toHaveCount(0)
  expect(await page.evaluate(()=>document.documentElement.scrollHeight)).toBeGreaterThan(viewport.height);expect(await page.evaluate(()=>document.documentElement.scrollWidth)).toBe(viewport.width)
  await page.getByRole('region',{name:'Karnataka emergency map'}).scrollIntoViewIfNeeded();await expect(page.getByRole('region',{name:'Karnataka emergency map'})).toBeVisible()
 }
 await page.setViewportSize({width:1366,height:768});await page.goto('/');await expect(page.locator('.home-viewport-fit')).toBeVisible()
 await page.evaluate(()=>document.documentElement.style.fontSize='200%');await expect(page.locator('.home-viewport-fit')).toHaveCount(0);expect(await page.evaluate(()=>document.documentElement.scrollHeight)).toBeGreaterThan(768);expect(await page.evaluate(()=>document.documentElement.scrollWidth)).toBe(1366)
 await page.getByText('Not connected',{exact:true}).scrollIntoViewIfNeeded();await expect(page.getByText('Not connected',{exact:true})).toBeVisible()
})
