// Called by local setup only. Credentials travel via stdin, never argv/env/files.
const {chromium}=require('../frontend/node_modules/playwright')
async function main(){
 let input='';for await(const part of process.stdin){input+=part;if(input.length>8192)throw Error('Input limit')}
 const {username,password,identity,origin}=JSON.parse(input);input=null
 if(!/^http:\/\/127\.0\.0\.1:(14180|14173)$/.test(origin))throw Error('Local origin required')
 const browser=await chromium.launch({headless:true})
 try{
  const context=await browser.newContext({baseURL:origin,viewport:{width:1366,height:768}})
  const page=await context.newPage();page.setDefaultTimeout(10000)
  await page.route('**/*',r=>new URL(r.request().url()).origin===origin?r.continue():r.abort())
  if((await page.request.get('/api/admin/session')).status()!==401)throw Error('Unexpected existing session')
  await page.goto('/admin');await page.getByLabel('Username',{exact:true}).fill(username);await page.getByLabel('Password',{exact:true}).fill(password)
  await page.getByRole('button',{name:'Sign in',exact:true}).click()
  await page.getByRole('button',{name:'Sign out',exact:true}).waitFor()
  const session=await page.request.get('/api/admin/session');if(session.status()!==200||(await session.json()).user.id!==identity)throw Error('Wrong account/database')
  const cookies=await context.cookies();if(!cookies.some(c=>c.httpOnly&&c.sameSite==='Strict'))throw Error('Session protections absent')
  const protectedURLs=['/api/admin/shelters?limit=1','/api/admin/reports?limit=1','/api/admin/notifications/options']
  for(const url of protectedURLs)if((await page.request.get(url)).status()!==200)throw Error('Workspace API unavailable')
  await page.getByRole('heading',{name:'Shelter assignments',exact:true}).waitFor()
  await page.getByRole('button',{name:'Citizen reports',exact:true}).click();await page.getByRole('heading',{name:'Citizen report moderation',exact:true}).waitFor()
  await page.getByRole('button',{name:'Telegram notifications',exact:true}).click();await page.getByRole('heading',{name:'Alerts — administrator-controlled Telegram notices',exact:true}).waitFor()
  await page.getByRole('button',{name:'Sign out',exact:true}).click();await page.getByRole('button',{name:'Sign in',exact:true}).waitFor()
  for(const url of ['/api/admin/session',...protectedURLs])if((await page.request.get(url)).status()!==401)throw Error('Session not revoked')
  process.stdout.write(JSON.stringify({login:true,shelter_management:true,citizen_moderation:true,alert_administration:true,logout:true,session_revoked:true,provider_mocks:false,alerts_sent:0}))
 }finally{await browser.close()}
}
main().catch(()=>{process.stderr.write('Local administrator browser verification failed; credentials were not logged.\n');process.exitCode=1})
