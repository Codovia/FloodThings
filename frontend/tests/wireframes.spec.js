import {test,expect} from '@playwright/test'

// No external services or operational writes in these layout/state tests.
test.beforeEach(async({page})=>{
 await page.route('**/*',route=>{
  const url=new URL(route.request().url());if(!['127.0.0.1','localhost'].includes(url.hostname))return route.abort()
  if(url.pathname==='/api/weather')return route.fulfill({status:200,contentType:'application/json',body:JSON.stringify({status:'available',retrieved_at:new Date().toISOString(),location:{latitude:+(url.searchParams.get('latitude')||12.9767936),longitude:+(url.searchParams.get('longitude')||77.590082)},grid_location:{latitude:13.25,longitude:74.95},current:{temperature_c:27,humidity_percent:80,precipitation_mm:0,valid_at:new Date().toISOString(),interval_seconds:900},forecast:Array.from({length:7},(_,i)=>({date:`2026-10-${10+i}`,weather_code:61,precipitation_mm:i,temperature_min_c:22,temperature_max_c:29}))})})
  return route.continue()
 })
})
test('sketches 1-3 have information left and a dominant map right at both desktop sizes',async({page})=>{
 for(const size of [{width:1366,height:768},{width:1920,height:1080}]){
  await page.setViewportSize(size)
  for(const route of ['/','/weather','/shelters']){
   await page.goto(route);const information=page.locator('.workspace-information'),map=page.locator('.workspace-map')
   await expect(map).toBeVisible();const left=await information.boundingBox(),right=await map.boundingBox()
   expect(right.x).toBeGreaterThan(left.x+left.width);expect(right.width).toBeGreaterThan(left.width)
   expect(right.height).toBeGreaterThan(350)
   expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true)
  }
 }
})
test('district selection survives all public routes; a historical cell never changes weather coordinates',async({page})=>{
 let weatherRequests=0;page.on('request',r=>{if(new URL(r.url()).pathname==='/api/weather')weatherRequests++})
 await page.goto('/weather');await expect(page.getByText('27 °C',{exact:true})).toBeVisible()
 await page.getByText('Change location',{exact:true}).click();await page.getByRole('button',{name:'Search districts and localities'}).click()
 await page.getByLabel('Karnataka district',{exact:true}).selectOption('nic:udupi.nic.in')
 const nav=page.getByRole('navigation',{name:'Main navigation'})
 await nav.getByRole('link',{name:'Flood Map',exact:true}).click();await expect(page.getByLabel('Flood Map district')).toHaveValue('nic:udupi.nic.in')
 await page.getByLabel('Historical evidence cell (keyboard alternative)').selectOption({index:1});await expect(page.getByRole('heading',{name:'Flood evidence details'})).toBeVisible()
 expect(weatherRequests).toBe(1)
 await nav.getByRole('link',{name:'Shelters',exact:true}).click()
 await expect(page.getByLabel('Karnataka district',{exact:true})).toHaveValue('nic:udupi.nic.in')
 await expect(page.getByText('No currently verified open shelters are available in this directory.')).toBeVisible()
 await nav.getByRole('link',{name:'Weather & AI',exact:true}).click()
 await expect(page.getByRole('heading',{name:'Bengaluru, Karnataka',exact:true})).toBeVisible();expect(weatherRequests).toBe(1)
 await expect(page.getByRole('button',{name:'Run experimental rainfall model'})).toBeDisabled()
})
test('mobile stacks the shared information and map, and exposes honest warning and hazard states',async({page})=>{
 await page.setViewportSize({width:390,height:844});await page.goto('/')
 await expect(page.getByText('Not connected',{exact:true})).toBeVisible()
 await expect(page.getByText(/does not establish that no emergency exists/)).toBeVisible()
 const left=await page.locator('.workspace-information').boundingBox(),map=await page.locator('.workspace-map').boundingBox()
 expect(map.y).toBeGreaterThan(left.y+left.height-1)
 await page.getByRole('button',{name:'Open navigation menu'}).click();await page.getByRole('navigation',{name:'Main navigation'}).getByRole('link',{name:'Flood Map',exact:true}).click()
 await page.getByLabel('Potential Flood-Prone Zones',{exact:true}).check()
 await expect(page.getByText('No verified potential flood-prone zone dataset is available for this district.',{exact:false})).toBeVisible()
 await expect(page.locator('.intelligence-map path[fill="#dc6047"]')).toHaveCount(56)
})
