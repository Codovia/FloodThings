import {test,expect} from '@playwright/test'
test.beforeEach(async({page})=>{await page.route('**/*',r=>['127.0.0.1','localhost'].includes(new URL(r.request().url()).hostname)?r.continue():r.abort())})
test('unconfigured real subscription endpoint gives no bot or delivery claim',async({page})=>{
 await page.goto('/alerts');await expect(page.getByText('Telegram subscriptions are not configured. Check official local warning channels.')).toBeVisible()
 await expect(page.getByRole('link',{name:'Open configured Telegram bot'})).toHaveCount(0)
})
test('configured fixture presents start/stop with no outbound Telegram request',async({page})=>{
 await page.route('**/api/alerts/subscription',r=>r.fulfill({json:{status:'available',url:'https://t.me/TEST_ONLY_FloodPulse_bot?start=floodpulse'}}))
 await page.goto('/alerts');await expect(page.getByRole('link',{name:'Open configured Telegram bot'})).toHaveAttribute('href','https://t.me/TEST_ONLY_FloodPulse_bot?start=floodpulse')
 await expect(page.getByText('/start floodpulse',{exact:true})).toBeVisible();await expect(page.getByText('/stop',{exact:true})).toBeVisible();await expect(page.getByText(/An attempt already in progress cannot be recalled/)).toBeVisible()
})
