import {test,expect} from '@playwright/test'
import {mkdir} from 'node:fs/promises'

// Presentation/layout fixtures only: all API requests intercepted, no persistence,
// external provider calls, credentials or notification sends.
const phase=process.env.FLOODPULSE_UI_EVIDENCE_PHASE||'after'
const output=new URL('../../docs/verification/ui_ux_2026_10_15/',import.meta.url).pathname
test.beforeEach(async({page})=>{
 await page.addInitScript(()=>Object.defineProperty(navigator,'geolocation',{value:{getCurrentPosition:(_yes,no)=>no({code:1})}}))
 await page.route('**/*',async route=>{
  const url=new URL(route.request().url())
  if(!['127.0.0.1','localhost'].includes(url.hostname))return route.abort()
  if(!url.pathname.startsWith('/api/'))return route.continue()
  const payload=url.pathname==='/api/environment'?{mode:'demonstration'}:
   url.pathname==='/api/shelters'?{status:'available',mode:'demonstration',shelters:[],retrieved_at:new Date().toISOString()}:
   url.pathname==='/api/alerts/subscription'?{status:'unavailable',message:'DEMO ONLY — Telegram is disabled in this isolated layout fixture.'}:
   {detail:'DEMO ONLY — service unavailable in layout fixture'}
  return route.fulfill({status:url.pathname.startsWith('/api/admin/')?401:['/api/environment','/api/shelters','/api/alerts/subscription'].includes(url.pathname)?200:503,contentType:'application/json',body:JSON.stringify(payload)})
 })
})
test('credential-free before/after desktop and mobile application evidence',async({page})=>{
 await mkdir(output,{recursive:true})
 for(const [path,name,width,height] of [['/','home-desktop',1366,768],['/report','report-mobile',390,844],['/admin','admin-login',1366,768]]){
  await page.setViewportSize({width,height});await page.goto(path)
  await expect(page.getByText('DEMO ONLY',{exact:true})).toBeVisible()
  await expect(page.locator('main h1')).toBeVisible()
  await page.screenshot({path:output+phase+'-'+name+'.png',fullPage:true})
 }
})
test('all public tasks reflow across mobile, tablet and desktop with recoverable failure states',async({page})=>{
 const errors=[];page.on('pageerror',e=>errors.push(e.message))
 for(const width of [320,390,768,1366]){
  await page.setViewportSize({width,height:width===1366?768:900})
  for(const path of ['/','/report','/shelters','/alerts','/admin','/weather','/flood-map']){
   await page.goto(path);await expect(page.locator('main h1')).toBeVisible()
   expect(await page.evaluate(()=>document.documentElement.scrollWidth)).toBe(width)
  }
 }
 expect(errors).toEqual([])
})

test('keyboard navigation, disclosure focus and enlarged-text reflow remain usable',async({page})=>{
 await page.setViewportSize({width:390,height:844});await page.goto('/')
 const menu=page.getByRole('button',{name:'Open navigation menu'})
 // Reach the menu using the keyboard from the route heading, including wraparound.
 for(let n=0;n<80&&!await menu.evaluate(el=>el===document.activeElement);n++)await page.keyboard.press('Tab')
 await expect(menu).toBeFocused();await page.keyboard.press('Enter')
 await expect(page.getByRole('navigation',{name:'Main navigation'})).toBeVisible()
 const report=page.getByRole('navigation',{name:'Main navigation'}).getByRole('link',{name:'Report an incident'})
 for(let n=0;n<15&&!await report.evaluate(el=>el===document.activeElement);n++)await page.keyboard.press('Tab')
 await expect(report).toBeFocused();await page.keyboard.press('Enter')
 await expect(page.locator('h1')).toBeFocused();await expect(page).toHaveTitle('Report an incident · FloodPulse')
 await page.keyboard.press('Tab');await expect(page.getByLabel('Event type')).toBeFocused()
 await page.setViewportSize({width:1366,height:768})
 await page.evaluate(()=>document.documentElement.style.fontSize='200%')
 for(const path of ['/','/report','/admin','/shelters']){
  await page.goto(path);await page.evaluate(()=>document.documentElement.style.fontSize='200%')
  await expect(page.locator('main h1')).toBeVisible()
  expect(await page.evaluate(()=>document.documentElement.scrollWidth)).toBe(1366)
 }
})

test('zoom-equivalent reflow and sampled text/control contrast',async({page})=>{
 // A 1366×768 desktop at 200% browser zoom has approximately 683×384 CSS px.
 // This checks equivalent reflow, not operation of Chrome's zoom menu.
 await page.setViewportSize({width:683,height:384})
 for(const path of ['/','/weather','/flood-map','/report','/shelters','/alerts','/admin']){
  await page.goto(path);await expect(page.locator('main h1')).toBeVisible()
  expect(await page.evaluate(()=>document.documentElement.scrollWidth)).toBe(683)
 }
 await page.setViewportSize({width:1366,height:768});await page.goto('/')
 for(const selector of ['.home-primary-actions .button-link','.home-primary-actions .secondary','.primary-nav a[aria-current]','.outlook-card h3']){
  const ratio=await page.locator(selector).first().evaluate(el=>{
   const channels=color=>color.match(/[\d.]+/g).slice(0,3).map(Number)
   const luminance=color=>channels(color).map(v=>{v/=255;return v<=.04045?v/12.92:((v+.055)/1.055)**2.4}).reduce((a,v,i)=>a+v*[.2126,.7152,.0722][i],0)
   const foreground=getComputedStyle(el).color
   let node=el,background=getComputedStyle(node).backgroundColor
   while(background==='rgba(0, 0, 0, 0)'&&node.parentElement){node=node.parentElement;background=getComputedStyle(node).backgroundColor}
   const values=[luminance(foreground),luminance(background)].sort((a,b)=>b-a)
   return (values[0]+.05)/(values[1]+.05)
  })
  expect(ratio).toBeGreaterThanOrEqual(4.5)
 }
})

test('administrator sections and exact preview stay explicit without a send',async({page})=>{
 let sends=0,previewRecord=null
 await page.route('**/api/locations/districts',route=>route.fulfill({contentType:'application/json',body:JSON.stringify({status:'available',items:[{id:'nic:udupi.nic.in',name:'Udupi'}],total:1})}))
 await page.route('**/api/admin/**',route=>{
  const path=new URL(route.request().url()).pathname
  if(path.endsWith('/send')){sends++;return route.abort()}
  if(path==='/api/admin/notifications'&&route.request().method()==='POST')previewRecord={id:'demo-preview',status:'draft',destination_label:'DEMO ONLY — mock destination',text:'DEMO ONLY — fixture preview; no delivery attempted.',content_sha256:'a'.repeat(64),created_at:new Date().toISOString(),created_by:'DEMO ONLY — fixture',kind:'informational'}
  const data=path==='/api/admin/session'?{mode:'demonstration',user:{id:'demo-only',username:'DEMO ONLY — layout fixture'},csrf_token:'nonsecret-layout-fixture'}:
   path.endsWith('/options')?{configured:true,destinations:[{id:'demo-only',label:'DEMO ONLY — mock destination',test_only:true,opted_in:true}],shelters:[]}:
   path==='/api/admin/notifications'&&route.request().method()==='POST'?previewRecord:
   {shelters:[],notifications:previewRecord?[previewRecord]:[],reports:[],total:previewRecord?1:0,mode:'demonstration'}
  return route.fulfill({contentType:'application/json',body:JSON.stringify(data)})
 })
 await page.setViewportSize({width:1366,height:768});await page.goto('/admin')
 for(const label of ['1. Facility identity and entrance','2. Capacity, facilities and contact','3. Availability and independent verification','4. Restrictions and internal notes'])await expect(page.getByRole('group',{name:label,exact:true})).toBeVisible()
 await page.screenshot({path:output+'after-admin-shelter-fixture.png',fullPage:true})
 await page.getByRole('button',{name:'Telegram notifications',exact:true}).click()
 await page.getByLabel('Telegram destination',{exact:true}).selectOption('demo-only')
 await page.getByLabel('Notification message',{exact:true}).fill('DEMO ONLY — fixture composition. Do not send.')
 await page.getByRole('button',{name:'Review exact notification'}).click()
 await expect(page.getByRole('heading',{name:'Exact message preview — DEMO ONLY — mock destination'})).toBeFocused()
 await expect(page.getByRole('button',{name:'Approve and send once through Telegram'})).toBeDisabled()
 expect(sends).toBe(0)
 await page.screenshot({path:output+'after-notification-preview-fixture.png'})
})
