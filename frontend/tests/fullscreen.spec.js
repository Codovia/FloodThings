import { withoutLiveRisk } from './liveData.js'
import { openTab, expectOneScreen } from './oneScreen.js'
import {test,expect} from '@playwright/test'
import { choosePlaceForHome } from './pointSelection.js'
const weather=()=>({status:'available',retrieved_at:new Date().toISOString(),current:{temperature_c:27,humidity_percent:80,precipitation_mm:0,valid_at:new Date().toISOString(),interval_seconds:900},grid_location:{latitude:13.25,longitude:74.95},forecast:Array.from({length:7},(_,i)=>({date:`2026-10-${10+i}`,weather_code:61,precipitation_mm:i,temperature_min_c:22,temperature_max_c:29}))})
test.beforeEach(async({page})=>{await page.route('**/*',route=>{const u=new URL(route.request().url());if(!['localhost','127.0.0.1'].includes(u.hostname))return route.abort();if(u.pathname==='/api/weather')return route.fulfill({status:200,contentType:'application/json',body:JSON.stringify({...weather(),location:u.searchParams.has('latitude')?{latitude:+u.searchParams.get('latitude'),longitude:+u.searchParams.get('longitude')}:null})});return route.continue()})})
test('desktop workspaces fit viewport, retain reachable internal panels and exclude public coordinate forms',async({page})=>{
 for(const size of [{width:1366,height:768},{width:1920,height:1080}]){
  await page.setViewportSize(size)
  for(const path of ['/','home-with-place','/flood-map','/shelters','/report','/alerts','/how-it-works','/admin']){
   // 'home-with-place': Home after choosing a place, with the seven-day weather strip (the Weather page was merged into Home).
   if(path==='home-with-place'){await page.goto('/shelters');await choosePlaceForHome(page,13.25,74.95);await expect(page.getByRole('list',{name:'Daily weather forecasts'})).toBeVisible()}else await page.goto(path);await expect(page.getByRole('heading',{level:1})).toBeVisible()
   await expect(page.getByLabel('Weather latitude')).toHaveCount(0);await expect(page.getByLabel('Weather longitude')).toHaveCount(0)
   expect(await page.evaluate(()=>[document.documentElement.scrollWidth,document.documentElement.scrollHeight])).toEqual([size.width,size.height])
   await page.waitForTimeout(800);expect(await expectOneScreen(page),path).toEqual({page:0,width:0,scrolls:0,outside:0})
   if(path==='/'){
    const frame=await page.getByRole('region',{name:'Karnataka emergency map'}).boundingBox()
    expect(frame.height).toBeGreaterThan(350);await page.getByRole('region',{name:'Karnataka emergency map'}).scrollIntoViewIfNeeded();await expect(page.getByRole('region',{name:'Karnataka emergency map'})).toBeVisible()
    await page.locator('.home-more-links').scrollIntoViewIfNeeded();await expect(page.getByRole('button',{name:'Refresh shelters'})).toHaveCount(0);await expect(page.locator('.home-river-line')).toHaveCount(0)
   }
   if(path==='/flood-map'){const frame=await page.locator('.intelligence-map').boundingBox(),footer=await page.locator('.app-footer').boundingBox();expect(frame.height).toBeGreaterThan(180);expect(frame.y+frame.height).toBeLessThanOrEqual(footer.y)}
   if(path==='home-with-place'){await expect(page.getByRole('list',{name:'Daily weather forecasts'}).getByRole('article')).toHaveCount(7);await expect(page.getByRole('button',{name:'Refresh weather'})).toBeEnabled();await page.getByRole('button',{name:'Rain chart'}).click();await expect(page.getByRole('list',{name:'Forecast daily precipitation chart'})).toBeVisible();await page.getByRole('button',{name:'Close',exact:true}).click()}
  }
 }
})
test('name-only district selection persists into Flood Map without inventing a weather point',async({page})=>{
 let requests=0;page.on('request',r=>{if(new URL(r.url()).pathname==='/api/weather')requests++})
 await page.goto('/');await page.getByRole('button',{name:'Search districts and localities'}).click();await page.getByLabel('Karnataka district').selectOption('nic:kodagu.nic.in')
 await expect(page.getByRole('status',{name:'District locality results'})).toContainText('No verified localities');await page.getByRole('button',{name:'Close place search'}).click();const before=requests;expect(before).toBe(0)
 await page.getByRole('navigation',{name:'Main navigation'}).getByRole('link',{name:'Flood Map',exact:true}).click();await expect(page.getByLabel('Go to district',{exact:true})).toHaveValue('nic:kodagu.nic.in');await openTab(page,'Past floods');await expect(page.getByText(/No past floods are mapped for this district/)).toBeVisible();expect(requests).toBe(before)
 await page.getByRole('button',{name:'Show all Karnataka'}).click();await expect(page.getByLabel('Go to district',{exact:true})).toHaveValue('')
})

// Not a risk test: answer live-risk requests in the browser (see liveData.js). Registered last, so it runs first.
test.beforeEach(async ({ page }) => { await withoutLiveRisk(page) })
