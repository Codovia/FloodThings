import {test,expect} from '@playwright/test'
const weather=()=>({status:'available',retrieved_at:new Date().toISOString(),current:{temperature_c:27,humidity_percent:80,precipitation_mm:0,valid_at:new Date().toISOString(),interval_seconds:900},grid_location:{latitude:13.25,longitude:74.95},forecast:Array.from({length:7},(_,i)=>({date:`2026-10-${10+i}`,weather_code:61,precipitation_mm:i,temperature_min_c:22,temperature_max_c:29}))})
test.beforeEach(async({page})=>{await page.route('**/*',route=>{const u=new URL(route.request().url());if(!['localhost','127.0.0.1'].includes(u.hostname))return route.abort();if(u.pathname==='/api/weather')return route.fulfill({status:200,contentType:'application/json',body:JSON.stringify({...weather(),location:u.searchParams.has('latitude')?{latitude:+u.searchParams.get('latitude'),longitude:+u.searchParams.get('longitude')}:null})});return route.continue()})})
test('desktop workspaces fit viewport, retain reachable internal panels and exclude public coordinate forms',async({page})=>{
 for(const size of [{width:1366,height:768},{width:1920,height:1080}]){
  await page.setViewportSize(size)
  for(const path of ['/','/weather','/flood-map','/shelters','/admin']){
   await page.goto(path);await expect(page.getByRole('heading',{level:1})).toBeVisible()
   await expect(page.getByLabel('Weather latitude')).toHaveCount(0);await expect(page.getByLabel('Weather longitude')).toHaveCount(0)
   expect(await page.evaluate(()=>[document.documentElement.scrollWidth,document.documentElement.scrollHeight])).toEqual([size.width,size.height])
   if(path==='/'){
    const frame=await page.getByRole('region',{name:'Weather location selection map'}).boundingBox(),footer=await page.locator('.app-footer').boundingBox()
    expect(frame.height).toBeGreaterThan(120);expect(frame.y+frame.height).toBeLessThanOrEqual(footer.y)
    await page.getByText('No currently verified open shelters are available in this directory.').scrollIntoViewIfNeeded();await expect(page.getByRole('button',{name:'Refresh shelters'})).toBeVisible()
   }
   if(path==='/flood-map'){const frame=await page.locator('.intelligence-map').boundingBox(),footer=await page.locator('.app-footer').boundingBox();expect(frame.height).toBeGreaterThan(180);expect(frame.y+frame.height).toBeLessThanOrEqual(footer.y)}
   if(path==='/weather'){await expect(page.getByRole('list',{name:'Daily weather forecasts'}).getByRole('article')).toHaveCount(7);await page.getByRole('list',{name:'Forecast daily precipitation chart'}).scrollIntoViewIfNeeded();await expect(page.getByRole('button',{name:'Refresh weather'})).toBeEnabled()}
  }
 }
})
test('name-only district selection persists into Flood Map without inventing a weather point',async({page})=>{
 let requests=0;page.on('request',r=>{if(new URL(r.url()).pathname==='/api/weather')requests++})
 await page.goto('/weather');await expect(page.getByText('27 °C',{exact:true})).toBeVisible();await page.getByText('Change location',{exact:true}).click();await page.getByRole('button',{name:'Search districts and localities'}).click();await page.getByLabel('Karnataka district').selectOption('nic:kodagu.nic.in')
 await expect(page.getByRole('status',{name:'District locality results'})).toContainText('No verified localities');const before=requests
 await page.getByRole('navigation',{name:'Main navigation'}).getByRole('link',{name:'Flood Map',exact:true}).click();await expect(page.getByLabel('Flood Map district',{exact:true})).toHaveValue('nic:kodagu.nic.in');await expect(page.getByText(/0 eligible historical cells/)).toBeVisible();expect(requests).toBe(before)
 await page.getByRole('button',{name:'Return to statewide view'}).click();await expect(page.getByLabel('Flood Map district',{exact:true})).toHaveValue('')
})
