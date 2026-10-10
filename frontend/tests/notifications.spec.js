import {test,expect} from '@playwright/test'

async function isolatedAdmin(page,configured=true){
 let authenticated=false,record=null,sends=0
 await page.route('**/*',route=>{const host=new URL(route.request().url()).hostname;return ['127.0.0.1','localhost'].includes(host)?route.continue():route.abort()})
 await page.route('**/api/admin/**',async route=>{
  const req=route.request(),path=new URL(req.url()).pathname;let data={},status=200
  if(path==='/api/admin/login'){authenticated=true;data={user:{id:'isolated-admin',username:'isolated-admin'},csrf_token:'ISOLATED_CSRF',mode:'demonstration'}}
  else if(!authenticated){status=401;data={detail:'Administrator login required'}}
  else if(path==='/api/admin/logout'){authenticated=false;data={status:'logged_out'}}
  else if(path.endsWith('/options'))data={configured,destinations:configured?[{id:'private-test',label:'Private test only',test_only:true}]:[],shelters:[],reason:configured?null:'Telegram credentials not configured'}
  else if(path==='/api/admin/shelters')data={shelters:[],total:0}
  else if(req.method()==='GET')data={notifications:record?[record]:[],total:record?1:0}
  else {
   expect(req.headers()['x-csrf-token']).toBe('ISOLATED_CSRF')
   const body=req.postDataJSON()
   if(path.endsWith('/send')){
    expect(body).toEqual({approve:true,content_sha256:'a'.repeat(64)});sends++
    record={...record,status:'accepted',result_code:'telegram_accepted',confirmed_at:new Date().toISOString(),attempted_at:new Date().toISOString(),completed_at:new Date().toISOString()};data=record
   }else{
    expect(body.destination_id).toBe('private-test');expect(body.request_id).toBeTruthy();expect(body.chat_id).toBeUndefined()
    record={id:'isolated-notice',created_by:'isolated-admin',destination_label:'Private test only',kind:body.kind,text:'DEMONSTRATION ONLY — simulated Telegram notice\n\n'+body.message,content_sha256:'a'.repeat(64),status:'draft',created_at:new Date().toISOString()};data=record;status=201
   }
  }
  await route.fulfill({status,contentType:'application/json',body:JSON.stringify(data)})
 })
 await page.goto('/admin');await page.getByLabel('Username',{exact:true}).fill('isolated-admin');await page.getByLabel('Password',{exact:true}).fill('ISOLATED TEST PASSWORD');await page.getByRole('button',{name:'Sign in'}).click()
 await expect(page.getByRole('heading',{name:'Alerts — administrator-controlled Telegram notices'})).toBeVisible()
 return ()=>sends
}

test('keyboard-accessible exact review, explicit confirmation and one simulated send',async({page})=>{
 const sends=await isolatedAdmin(page)
 await page.getByLabel('Telegram destination',{exact:true}).selectOption('private-test')
 await page.getByLabel('Notification message',{exact:true}).fill('Isolated browser demonstration. Not an emergency announcement.')
 await page.getByRole('button',{name:'Review exact notification'}).click()
 await expect(page.getByRole('heading',{name:'Exact message preview — Private test only'})).toBeVisible()
 const send=page.getByRole('button',{name:'Approve and send once through Telegram'});await expect(send).toBeDisabled();expect(sends()).toBe(0)
 const confirm=page.getByRole('checkbox',{name:/I reviewed this exact message/});await confirm.focus();await page.keyboard.press('Space');await expect(send).toBeEnabled();await send.click()
 await expect(page.getByLabel('Notification preview').getByText(/Telegram accepted the message/)).toBeVisible();expect(sends()).toBe(1)
 await expect(page.getByText(/Recipient reading is not confirmed/).first()).toBeVisible()
 await page.getByRole('button',{name:'Refresh notification history'}).click();expect(sends()).toBe(1)
 await expect(page.getByRole('heading',{name:'Shelter assignments'})).toBeVisible()
 await page.getByRole('button',{name:'Sign out'}).click();await expect(page.getByRole('button',{name:'Sign in'})).toBeVisible()
})

test('mobile missing-configuration state preserves shelter management and sends nothing',async({page})=>{
 await page.setViewportSize({width:390,height:844});const sends=await isolatedAdmin(page,false)
 await expect(page.getByText(/Telegram credentials not configured/)).toBeVisible();await expect(page.getByRole('button',{name:'Review exact notification'})).toBeDisabled()
 await expect(page.getByRole('button',{name:'Save shelter assignment'})).toBeVisible();expect(sends()).toBe(0)
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true)
})

test('lost send response remains uncertain and offers no repeated-send action',async({page})=>{
 await isolatedAdmin(page)
 await page.route('**/api/admin/notifications/*/send',r=>r.fulfill({status:503,contentType:'application/json',body:JSON.stringify({detail:'Attempt started but result could not be recorded. Delivery may have occurred; do not resend.'})}))
 await page.getByLabel('Telegram destination').selectOption('private-test');await page.getByLabel('Notification message').fill('Isolated failure demonstration only');await page.getByRole('button',{name:'Review exact notification'}).click()
 await page.getByRole('checkbox',{name:/I reviewed this exact message/}).check();await page.getByRole('button',{name:'Approve and send once through Telegram'}).click()
 await expect(page.getByRole('region',{name:'Alerts — administrator-controlled Telegram notices'}).getByRole('alert')).toContainText('Delivery may have occurred');await expect(page.getByLabel('Notification preview').getByText(/outcome not recorded/)).toBeVisible()
 await expect(page.getByRole('button',{name:'Approve and send once through Telegram'})).toHaveCount(0)
})
