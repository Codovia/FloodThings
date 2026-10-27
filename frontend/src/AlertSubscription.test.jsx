import React from 'react'
import {cleanup,render,screen,fireEvent} from '@testing-library/react'
import {afterEach,expect,it,vi} from 'vitest'
import AlertSubscription from './AlertSubscription.jsx'
afterEach(()=>{cleanup();vi.unstubAllGlobals()})
// The official-warnings section has its own public links; no subscriber link may appear outside it.
const subscriberLinks=()=>screen.queryAllByRole('link').filter(a=>!a.closest('.alert-official')||/t\.me|unapproved/.test(a.getAttribute('href')))
it('shows honest unavailable setup without a manufactured bot',async()=>{
 vi.stubGlobal('fetch',vi.fn(async()=>({ok:true,json:async()=>({status:'unavailable',message:'Telegram subscriptions are not configured.'})})))
 render(<AlertSubscription/>);await screen.findByText('Telegram subscriptions are not configured.');expect(subscriberLinks()).toEqual([])
})
it('configured bot exposes explicit start/stop and membership limits without any send',async()=>{
 vi.stubGlobal('fetch',vi.fn(async()=>({ok:true,json:async()=>({status:'available',url:'https://t.me/TEST_ONLY_bot?start=floodpulse'})})))
 render(<AlertSubscription/>);await screen.findByRole('link',{name:'Open configured Telegram bot'});expect(screen.getByText('/stop')).toBeTruthy();expect(fetch).toHaveBeenCalledTimes(1);expect(fetch.mock.calls[0][0]).toBe('/api/alerts/subscription')
})
it('invalid external links never become subscriber destinations',async()=>{
 vi.stubGlobal('fetch',vi.fn(async()=>({ok:true,json:async()=>({status:'available',url:'https://unapproved.test/track'})})))
 render(<AlertSubscription/>);await screen.findByText('Telegram subscription setup could not be checked.');expect(subscriberLinks()).toEqual([])
})
it('offers an explicit retry after unavailable setup without attempting delivery',async()=>{
 const fetcher=vi.fn().mockResolvedValueOnce({ok:false,json:async()=>({})}).mockResolvedValueOnce({ok:true,json:async()=>({status:'available',url:'https://t.me/TEST_ONLY_bot?start=floodpulse'})})
 vi.stubGlobal('fetch',fetcher);render(<AlertSubscription/> )
 fireEvent.click(await screen.findByRole('button',{name:'Check subscription setup again'}))
 await screen.findByRole('link',{name:'Open configured Telegram bot'})
 expect(fetcher.mock.calls.map(([url])=>url)).toEqual(['/api/alerts/subscription','/api/alerts/subscription'])
})
it('always points to official warnings and verified emergency numbers, separate from project notices',async()=>{
 vi.stubGlobal('fetch',vi.fn(async()=>({ok:true,json:async()=>({status:'unavailable',message:'Telegram subscriptions are not configured.'})})))
 render(<AlertSubscription navigate={vi.fn()}/>);await screen.findByText('Telegram subscriptions are not configured.')
 expect(screen.getByRole('link',{name:'NDMA SACHET'}).getAttribute('href')).toBe('https://sachet.ndma.gov.in/');expect(screen.getByRole('link',{name:'112'}).getAttribute('href')).toBe('tel:112');expect(screen.getByRole('link',{name:'080-1070'}).getAttribute('href')).toBe('tel:0801070')
})
it('a chosen district gives its own bot link and command; links to anything else are dropped',async()=>{
 const base='https://t.me/TEST_ONLY_bot?start=floodpulse'
 vi.stubGlobal('fetch',vi.fn(async()=>({ok:true,json:async()=>({status:'available',url:base,districts:[
  {name:'Udupi',url:base+'_udupi',command:'/start floodpulse udupi'},{name:'Dakshina Kannada',url:base+'_dakshina_kannada',command:'/start floodpulse dakshina kannada'},
  {name:'Fake',url:'https://unapproved.test/x',command:'/start floodpulse fake'},{name:'Other bot',url:'https://t.me/OTHER_bot?start=floodpulse_udupi',command:'/start floodpulse udupi'}]})})))
 render(<AlertSubscription/>);const select=await screen.findByLabelText('Your district')
 expect([...select.options].map(o=>o.textContent)).toEqual(['Choose your district','Udupi','Dakshina Kannada'])
 fireEvent.change(select,{target:{value:'Dakshina Kannada'}})
 expect(screen.getByRole('link',{name:'Get Dakshina Kannada alerts in Telegram'}).getAttribute('href')).toBe(base+'_dakshina_kannada')
 expect(screen.getByText('/start floodpulse dakshina kannada')).toBeTruthy();expect(subscriberLinks().some(a=>/unapproved|OTHER_bot/.test(a.getAttribute('href')))).toBe(false)
})
