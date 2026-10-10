import {expect,test} from '@playwright/test'
import {readFileSync} from 'node:fs'
const model=JSON.parse(readFileSync(new URL('../../backend/models/rainfall_logistic_v1/model.json',import.meta.url)))
const metadata=JSON.parse(readFileSync(new URL('../../backend/models/rainfall_logistic_v1/metadata.json',import.meta.url)))
const now='2026-10-09T13:30:00Z'
// Explicit offline browser-contract fixtures. Real provider/model integration
// is demonstrated separately; these values are never application defaults.
const weather=point=>({status:'available',retrieved_at:now,location:point,grid_location:{latitude:13.6,longitude:74.7},
 current:{temperature_c:27,humidity_percent:80,precipitation_mm:0,interval_seconds:900,valid_at:now},prediction_status:'not_available',
 forecast:Array.from({length:7},(_,i)=>({date:`2026-10-${String(i+9).padStart(2,'0')}`,temperature_min_c:22,temperature_max_c:30,precipitation_mm:i,weather_code:61}))})
const inference=point=>{
 const features={rain_24h_mm:24,rain_72h_mm:72,max_hourly_rain_24h_mm:1,temperature_mean_24h_c:27,humidity_mean_24h_percent:80,pressure_mean_24h_hpa:1005,season_sin:0,season_cos:1}
 const score=model.feature_order.reduce((sum,f,i)=>sum+(features[f]-model.scaler.mean[i])/model.scaler.scale[i]*model.logistic_regression.coefficients[i],model.logistic_regression.intercept)
 return {status:'available',experimental:true,model_version:metadata.version,model_sha256:metadata.model_sha256,location:point,
 prediction:score>0?'heavy_rainfall_predicted':'below_heavy_threshold_predicted',prediction_text:score>0?'At least 64.5 mm predicted by the experimental model':'Below 64.5 mm predicted by the experimental model',
 probability:null,features,feature_valid_through_utc:'2026-10-09T13:00:00Z',retrieved_at:now,provider_grid:{latitude:13.6,longitude:74.7},target:metadata.target,
 validation:{model_type:'Logistic Regression',...metadata.holdout_metrics,samples:metadata.testing.samples},
 horizon:{hours:24,start_utc:'2026-10-09T14:00:00Z',end_utc:'2026-10-10T14:00:00Z'}}
}
const choose=(page,name)=>page.getByRole('list',{name:'District localities'}).getByRole('button',{name:new RegExp('^'+name+' —')}).click()
test.beforeEach(async({page})=>{
 await page.clock.install({time:new Date(now)});await page.clock.pauseAt(new Date(now))
 await page.route('**/*',route=>{
  const u=new URL(route.request().url());if(!['127.0.0.1','localhost'].includes(u.hostname))return route.abort()
  const point={latitude:+u.searchParams.get('latitude'),longitude:+u.searchParams.get('longitude')}
  if(u.pathname==='/api/weather')return route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(weather(point))})
  if(u.pathname==='/api/ai/rainfall-outlook')return route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(inference(point))})
  return route.continue()
 })
})

test('PostgreSQL directory, locality switch, model display, seven days and six-hour isolation',async({page})=>{
 let weatherCalls=0,aiCalls=0
 page.on('request',r=>{const p=new URL(r.url()).pathname;if(p==='/api/weather')weatherCalls++;if(p==='/api/ai/rainfall-outlook')aiCalls++})
 await page.goto('/');await page.getByRole('button',{name:'Search districts and localities'}).click()
 await page.getByLabel('Karnataka district').selectOption('nic:udupi.nic.in');await choose(page,'Kundapur')
 await expect(page.getByRole('heading',{name:'Kundapur, Udupi'})).toBeVisible()
 await expect(page.getByRole('list',{name:'Daily weather forecasts'}).getByRole('article')).toHaveCount(7)
 await page.getByRole('button',{name:'Run experimental rainfall model'}).click()
 await expect(page.getByText(/64.5 mm predicted by the experimental model/)).toBeVisible();expect(aiCalls).toBe(1)
 await expect(page.getByText(/Model rainfall_logistic_v1/)).toBeVisible()
 await expect(page.getByText(/precision: 14.50% · recall: 91.67%/)).toBeVisible()
 await page.getByLabel('Karnataka district').selectOption('nic:dk.nic.in');await choose(page,'Mangaluru')
 await expect(page.getByRole('heading',{name:'Mangaluru, Dakshina Kannada'})).toBeVisible()
 await expect.poll(()=>aiCalls).toBe(2)
 await expect(page.getByText(/Mangaluru, Dakshina Kannada · next 24/)).toBeVisible()
 expect(weatherCalls).toBe(3)
 await expect(page.getByText(/Flood prediction is not available/)).toBeVisible()
 const before=aiCalls;await page.clock.fastForward(6*60*60*1000-1);expect(aiCalls).toBe(before)
 // No duplicate model call for render/visibility changes while weather is fresh.
 await page.evaluate(()=>{window.dispatchEvent(new Event('focus'));window.dispatchEvent(new Event('online'))});expect(aiCalls).toBe(before)
})

test('provider/model outage clears predictions without affecting weather and mobile manual selection',async({page})=>{
 await page.setViewportSize({width:390,height:844});await page.goto('/')
 await page.getByRole('button',{name:'Search districts and localities'}).click();await page.getByLabel('Karnataka district').selectOption('nic:udupi.nic.in');await choose(page,'Kundapur')
 await page.getByRole('button',{name:'Run experimental rainfall model'}).click();await expect(page.getByText(/64.5 mm predicted by the experimental model/)).toBeVisible()
 await page.route('**/api/ai/rainfall-outlook?**',r=>r.fulfill({status:503,contentType:'application/json',body:JSON.stringify({status:'unavailable',message:'Controlled model input outage',prediction:null})}))
 await page.getByRole('button',{name:'Retry rainfall outlook'}).click()
 await expect(page.getByRole('alert',{name:'AI rainfall outlook error'})).toContainText('Controlled model input outage')
 await expect(page.getByText(/64.5 mm predicted by the experimental model/)).toHaveCount(0)
 await expect(page.getByRole('list',{name:'Daily weather forecasts'}).getByRole('article')).toHaveCount(7)
 await page.getByLabel('Weather latitude').fill('14');await page.getByLabel('Weather longitude').fill('75');await page.getByRole('button',{name:'Get point weather'}).click()
 await expect(page.getByRole('heading',{name:'Entered coordinates'})).toBeVisible()
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true)
})
