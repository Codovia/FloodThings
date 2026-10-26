import { withoutLiveRisk } from './liveData.js'
import { test, expect } from '@playwright/test'
import { expectOneScreen, openTab } from './oneScreen.js'
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
const NONE={page:0,width:0,scrolls:0,outside:0}
// One-screen rule (20 Oct 2026): Home never scrolls at laptop or phone sizes; details open as popups inside the screen.
for(const viewport of [{width:1366,height:768},{width:1508,height:761},{width:1600,height:900},{width:1920,height:1080}])test(`Home fits ${viewport.width}x${viewport.height} on one screen, with essentials and popups inside it`,async({page})=>{
 await page.setViewportSize(viewport);await page.goto('/');await expect(page.getByRole('region',{name:'Karnataka emergency map'})).toBeVisible()
 expect(await page.evaluate(()=>[innerHeight,document.documentElement.scrollHeight,document.documentElement.scrollWidth])).toEqual([viewport.height,viewport.height,viewport.width])
 for(const selector of ['.app-header','.app-footer','.home-location-bar','.home-essential-status','.imd-card','.sachet-card','.risk-area','.home-flood-map'])await bounded(page.locator(selector),viewport)
 const main=await page.locator('main').boundingBox(),map=await bounded(page.locator('.home-map-stage'),viewport)
 expect(map.width/main.width).toBeGreaterThan(.5);expect((await page.locator('.home-flood-map').boundingBox()).height).toBeGreaterThan(300)
 await page.waitForTimeout(1600);expect(await page.evaluate(()=>document.documentElement.dataset.fit||null)).toBeNull();expect(await expectOneScreen(page)).toEqual(NONE)
 await page.getByRole('button',{name:'Data sources & privacy'}).click();const sources=page.getByRole('dialog',{name:'Data sources, freshness & privacy'})
 await expect(sources.getByText(/Open-Meteo model output, CC BY 4.0/)).toBeVisible();await bounded(sources,viewport);await page.keyboard.press('Escape');await expect(sources).toHaveCount(0)
 await expect(page.getByRole('button',{name:'Data sources & privacy'})).toBeFocused()
 await page.getByRole('button',{name:'Map sources & limitations'}).click();await expect(page.getByText(/State outline: simplified 2011 context/)).toBeVisible();await bounded(page.getByRole('dialog'),viewport)
 await page.getByRole('button',{name:'Close',exact:true}).click();expect(await page.evaluate(()=>scrollY)).toBe(0)
})
test('Home keeps keyboard name search accessible without moving the desktop document',async({page})=>{
 await page.setViewportSize({width:1366,height:768});await page.goto('/')
 const search=page.getByRole('button',{name:'Search districts and localities'});await search.focus();await page.keyboard.press('Enter')
 await expect(page.getByLabel('Karnataka district',{exact:true})).toBeVisible();await bounded(page.locator('.directory-content'),{width:1366,height:768});expect(await page.evaluate(()=>document.documentElement.scrollHeight)).toBe(768)
 await page.getByRole('button',{name:'Close place search'}).click();await expect(page.locator('.directory-content')).toHaveCount(0)
})
test('phones fit one screen: Warnings, Risk and Map are tabs',async({page})=>{
 for(const viewport of [{width:390,height:844},{width:390,height:700}]){
  await page.setViewportSize(viewport);await page.goto('/');await expect(page.getByRole('tab',{name:'Warnings'})).toBeVisible()
  for(const tab of ['Warnings','Risk','Map']){await openTab(page,tab);await page.waitForTimeout(400);expect(await expectOneScreen(page),`${viewport.height} ${tab}`).toEqual(NONE)}
  await expect(page.getByRole('region',{name:'Karnataka emergency map'})).toBeVisible()
  expect(await page.evaluate(()=>document.documentElement.dataset.fit||null)).toBeNull()
 }
})
test('very short windows and enlarged text fall back to scrolling instead of hiding content',async({page})=>{
 // Safety net: content that would be cut off is never hidden; the page scrolls instead.
 await page.setViewportSize({width:1366,height:420});await page.goto('/')
 await expect.poll(()=>page.evaluate(()=>document.documentElement.dataset.fit||null)).toBe('scroll')
 expect(await page.evaluate(()=>document.documentElement.scrollHeight)).toBeGreaterThan(420)
 await page.getByRole('region',{name:'Karnataka emergency map'}).scrollIntoViewIfNeeded();await expect(page.getByRole('region',{name:'Karnataka emergency map'})).toBeInViewport()
 await page.setViewportSize({width:1366,height:768});await expect.poll(()=>page.evaluate(()=>document.documentElement.dataset.fit||null)).toBeNull()
 await page.addInitScript(()=>document.addEventListener('DOMContentLoaded',()=>{document.documentElement.style.fontSize='200%'}));await page.goto('/')
 await expect.poll(()=>page.evaluate(()=>document.documentElement.dataset.fit||null)).toBe('scroll')
 await page.locator('.risk-area').scrollIntoViewIfNeeded();await expect(page.locator('.risk-area')).toBeInViewport();expect(await page.evaluate(()=>document.documentElement.scrollWidth)).toBe(1366)
})

// Not a risk test: answer live-risk requests in the browser (see liveData.js). Registered last, so it runs first.
test.beforeEach(async ({ page }) => { await withoutLiveRisk(page) })
