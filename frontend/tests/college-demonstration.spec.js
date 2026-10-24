import {test,expect} from '@playwright/test'
import {mkdir,writeFile} from 'node:fs/promises'

const evidence='/tmp/floodpulse-college-rehearsal/browser'
test.skip(!process.env.FLOODPULSE_REPORT_TEST_PASSWORD,'Requires the UUID-isolated demonstration runner')

test('college rehearsal: real isolated login, CSRF, logout and desktop/mobile workspaces without sending alerts',async({page})=>{
 test.setTimeout(90000)
 await mkdir(evidence,{recursive:true,mode:0o700})
 await page.route('**/*',r=>['127.0.0.1','localhost'].includes(new URL(r.request().url()).hostname)?r.continue():r.abort())
 expect((await (await page.request.get('/api/shelters')).json()).mode).toBe('demonstration')
 const urls=['/api/admin/session','/api/admin/shelters','/api/admin/reports','/api/admin/reports/evidence','/api/admin/notifications/options']
 for(const url of urls)expect((await page.request.get(url)).status()).toBe(401)
 await page.setViewportSize({width:1366,height:768})
 await page.goto('/admin')
 await expect(page.getByText('DEMO ONLY',{exact:true})).toBeVisible()
 await page.getByLabel('Username',{exact:true}).fill('test-report-admin')
 await page.getByLabel('Password',{exact:true}).fill(process.env.FLOODPULSE_REPORT_TEST_PASSWORD)
 await page.getByRole('button',{name:'Sign in',exact:true}).click()
 await expect(page.getByRole('button',{name:'Sign out',exact:true})).toBeVisible()
 const cookies=await page.context().cookies()
 expect(cookies.some(c=>c.httpOnly&&c.sameSite==='Strict')).toBe(true)
 for(const url of urls)expect((await page.request.get(url)).status()).toBe(200)
 expect((await page.request.post('/api/admin/logout')).status()).toBe(403)
 expect((await page.request.post('/api/admin/logout',{headers:{Origin:'http://127.0.0.1:14173','X-CSRF-Token':'invalid-fixture-token'}})).status()).toBe(403)
 for(const [tab,heading] of [['Shelter workspace','Shelter assignments'],['Citizen reports','Citizen report moderation'],['Telegram notifications','Alerts — administrator-controlled Telegram notices']]){
  await page.getByRole('button',{name:tab,exact:true}).click()
  await expect(page.getByRole('heading',{name:heading,exact:true})).toBeVisible()
 }
 await page.setViewportSize({width:390,height:844})
 expect(await page.evaluate(()=>document.documentElement.scrollWidth)).toBe(390)
 await page.screenshot({path:evidence+'/admin-mobile.png',fullPage:true})
 await page.getByRole('button',{name:'Sign out',exact:true}).click()
 await expect(page.getByRole('button',{name:'Sign in',exact:true})).toBeVisible()
 for(const url of urls)expect((await page.request.get(url)).status()).toBe(401)
 const layouts=[]
 for(const [path,name] of [['/','home'],['/report','report'],['/shelters','shelters'],['/alerts','alerts']]){
  await page.goto(path);await expect(page.locator('main')).toBeVisible()
  const width=await page.evaluate(()=>document.documentElement.scrollWidth)
  expect(width).toBe(390);layouts.push({page:name,width,viewport:390})
  await page.screenshot({path:evidence+'/'+name+'-mobile.png',fullPage:true})
 }
 await writeFile(evidence+'/rehearsal.json',JSON.stringify({isolated:true,browser:'installed Chrome via audit configuration',
  login:true,protected_workspaces:true,csrf_missing_and_invalid_denied:true,logout_revoked:true,layouts,
  external_browser_requests:'blocked',notification_previews_created:0,send_endpoints_called:0},null,2),{mode:0o600})
})
