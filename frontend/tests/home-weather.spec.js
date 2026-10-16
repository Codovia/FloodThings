import {test,expect} from '@playwright/test'
import {readFileSync} from 'node:fs'
// Recorded response supplies format/values; routing and GPS are isolated TEST fixtures.
const record=JSON.parse(readFileSync(new URL('../../backend/tests/fixtures/open_meteo_kundapur.json',import.meta.url))).payload
const reference='2026-10-13T06:20:00Z',hour=3600000
function fixture(location){
 const c=record.current
 return {status:'available',location,grid_location:{latitude:record.latitude,longitude:record.longitude},retrieved_at:reference,forecast_issued_at:null,
 current:{temperature_c:c.temperature_2m,humidity_percent:c.relative_humidity_2m,precipitation_mm:c.precipitation,weather_code:c.weather_code,wind_speed:c.wind_speed_10m,wind_speed_unit:record.current_units.wind_speed_10m,interval_seconds:c.interval,valid_at:c.time+':00+05:30'},
 forecast:record.daily.time.map((date,i)=>({date,temperature_min_c:record.daily.temperature_2m_min[i],temperature_max_c:record.daily.temperature_2m_max[i],precipitation_mm:record.daily.precipitation_sum[i],weather_code:record.daily.weather_code[i]})),
 hourly_precipitation:{status:'available',timezone:'Asia/Kolkata',unit:'mm',interval_seconds:3600,interval_semantics:'preceding_hour',source:{name:'Open-Meteo'},intervals:record.hourly.time.map((time,i)=>({start:new Date(Date.parse(time+':00+05:30')-hour).toISOString(),end:time+':00+05:30',precipitation_mm:record.hourly.precipitation[i],unit:'mm'}))}}
}
async function setup(page,missing=false){
 const calls=[]
 await page.clock.install({time:new Date(reference)})
 await page.addInitScript(()=>Object.defineProperty(navigator,'geolocation',{value:{getCurrentPosition:yes=>yes({coords:{latitude:13.4,longitude:74.7,accuracy:40},timestamp:Date.now()})}}))
 await page.route('**/*',route=>{
  const u=new URL(route.request().url())
  if(!['localhost','127.0.0.1'].includes(u.hostname)){
   if(u.hostname==='tile.openstreetmap.org')return route.fulfill({status:200,contentType:'image/png',body:Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aS1cAAAAASUVORK5CYII=','base64')})
   return route.abort()
  }
  if(u.pathname==='/api/weather'){
   calls.push(u.search);const b=fixture({latitude:+u.searchParams.get('latitude'),longitude:+u.searchParams.get('longitude')});if(missing)b.hourly_precipitation.intervals[14].precipitation_mm=null
   return route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(b)})
  }
  if(u.pathname==='/api/shelters')return route.fulfill({status:200,contentType:'application/json',body:JSON.stringify({status:'available',mode:'live',shelters:[],retrieved_at:reference})})
  return route.continue()
 });return calls
}
for(const viewport of [{width:1366,height:768},{width:1600,height:900},{width:1920,height:1080},{width:390,height:844}])test(`current weather and hourly rainfall preserve ${viewport.width}x${viewport.height} workspace`,async({page})=>{
 const calls=await setup(page);await page.setViewportSize(viewport);await page.goto('/')
 await expect(page.getByRole('heading',{name:'35.5 °C',exact:true})).toBeVisible()
 await expect(page.getByRole('heading',{name:'Next 24 full forecast hours: 0 mm'})).toBeVisible()
 await expect(page.getByText(/Humidity: 35%\. Wind: 13.3 km\/h/)).toBeVisible()
 await expect(page.locator('.home-rain-summary')).toContainText('13 Oct 2026, 12:00 pm IST to 14 Oct 2026, 12:00 pm IST')
 await expect(page.getByLabel('Flood and drainage risk')).toBeVisible()
 expect(calls).toHaveLength(1)
 const size=await page.evaluate(()=>({height:document.documentElement.scrollHeight,width:document.documentElement.scrollWidth}));expect(size.width).toBe(viewport.width)
 if(viewport.width>=1100){
  expect(size.height).toBe(viewport.height)
  const map=await page.locator('.home-flood-map').boundingBox();expect(map.height).toBeGreaterThan(300)
  const cards=await page.locator('.home-summary-card').all();for(const card of cards){const r=await card.boundingBox();expect(r.y+r.height).toBeLessThan(viewport.height)}
  await page.getByRole('region',{name:'Additional area information'}).focus();await page.keyboard.press('End');expect(await page.evaluate(()=>scrollY)).toBe(0)
  await expect(page.locator('.official-summary')).toBeVisible()
 }else expect(size.height).toBeGreaterThan(viewport.height)
 if(viewport.width<1100)await page.getByRole('button',{name:'Open navigation menu'}).click()
 await page.evaluate(()=>{history.pushState(null,'','/weather');dispatchEvent(new PopStateEvent('popstate'))})
 await expect(page.getByRole('list',{name:'Daily weather forecasts'}).getByRole('article')).toHaveCount(7)
 if(viewport.width<1100)await page.getByRole('button',{name:'Open navigation menu'}).click()
 await page.getByRole('navigation',{name:'Main navigation'}).getByRole('link',{name:'Home',exact:true}).click();await expect(page.getByRole('heading',{name:'35.5 °C',exact:true})).toBeVisible();expect(calls).toHaveLength(1)
})
test('one null hour makes the whole total unavailable while keeping valid current weather',async({page})=>{
 await setup(page,true);await page.goto('/');await expect(page.getByRole('heading',{name:'Next-24-hour total unavailable'})).toBeVisible();await expect(page.getByRole('heading',{name:'35.5 °C',exact:true})).toBeVisible();await page.getByText('Data sources, freshness & privacy',{exact:true}).click();await expect(page.getByText(/Exactly 24 ordered, consecutive one-hour intervals/)).toBeVisible()
 await expect(page.getByLabel('Flood and drainage risk')).toBeVisible()
})
