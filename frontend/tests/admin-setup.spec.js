import {test,expect} from '@playwright/test'
import {execFileSync} from 'node:child_process'
test.skip(!process.env.FLOODPULSE_REPORT_TEST_PASSWORD,'Requires UUID-isolated provisioning runner')
test('local setup browser verifier uses real login, all admin workspaces and logout without exporting maintenance credentials',async({request})=>{
 const password=process.env.FLOODPULSE_REPORT_TEST_PASSWORD
 const login=await request.post('/api/admin/login',{headers:{Origin:'http://127.0.0.1:14173','X-FloodPulse-Login':'1'},data:{username:'test-report-admin',password}})
 expect(login.status()).toBe(200);const session=await login.json()
 const logout=await request.post('/api/admin/logout',{headers:{Origin:'http://127.0.0.1:14173','X-CSRF-Token':session.csrf_token}});expect(logout.status()).toBe(200)
 const env=Object.fromEntries(Object.entries(process.env).filter(([key])=>!key.includes('DATABASE')&&!key.startsWith('TELEGRAM_')&&!['LOCATION_DIRECTORY_ADMIN_URL','FLOODPULSE_REPORT_TEST_PASSWORD'].includes(key)))
 const output=execFileSync('node',['../scripts/verify_admin_login.cjs'],{input:JSON.stringify({username:'test-report-admin',password,identity:session.user.id,origin:'http://127.0.0.1:14173'}),env,encoding:'utf8',timeout:45000})
 expect(JSON.parse(output)).toEqual({login:true,shelter_management:true,citizen_moderation:true,alert_administration:true,logout:true,session_revoked:true,provider_mocks:false,alerts_sent:0})
 expect(output).not.toContain(password);expect(output).not.toContain('csrf_token')
})
