import React from 'react'
import {cleanup,fireEvent,render,screen,waitFor} from '@testing-library/react'
import {afterEach,beforeEach,expect,it,vi} from 'vitest'
import CitizenReport from './CitizenReport.jsx'
vi.mock('./ShelterMap.jsx',()=>({default:()=> <div>Report map fixture</div>}))
let gps
beforeEach(()=>{vi.stubGlobal('isSecureContext',true);gps=vi.fn(yes=>yes({coords:{latitude:13.4,longitude:74.7,accuracy:1200},timestamp:Date.now()}));Object.defineProperty(navigator,'geolocation',{configurable:true,value:{getCurrentPosition:gps}});vi.stubGlobal('fetch',vi.fn(async()=>({ok:true,json:async()=>({id:'TEST ONLY report',state:'SUBMITTED',source:'USER_REPORTED',received_at:new Date().toISOString(),message:'Private fixture receipt'})})))})
afterEach(()=>{cleanup();vi.unstubAllGlobals();delete navigator.geolocation})
it('requires deliberate GPS and review consent before submission; no automatic camera access',async()=>{
 render(<CitizenReport/>);expect(gps).not.toHaveBeenCalled();expect(fetch).not.toHaveBeenCalled();expect(screen.getByRole('button',{name:'Review report'}).disabled).toBe(true)
 fireEvent.change(screen.getByLabelText('What did you see?'),{target:{value:'TEST ONLY blocked drainage fixture'}})
 fireEvent.click(screen.getByRole('button',{name:'Use GPS for this report'}));expect(gps).toHaveBeenCalledTimes(1)
 fireEvent.click(screen.getByLabelText(/I consent to private admin review/));fireEvent.click(screen.getByRole('button',{name:'Review report'}));expect(fetch).not.toHaveBeenCalled()
 fireEvent.click(screen.getByRole('button',{name:'Submit for private review'}));await screen.findByText(/Report TEST ONLY report/)
 const body=JSON.parse(fetch.mock.calls[0][1].body);expect(body.accuracy_m).toBe(1200);expect(body.consent).toBe(true);expect(body.photo_base64).toBeUndefined()
 expect(body.withdrawal_secret).toMatch(/^[a-f0-9]{64}$/)
})
it('denied GPS cannot silently become a network position',()=>{
 gps.mockImplementation((_,no)=>no({code:1}));render(<CitizenReport/>);fireEvent.click(screen.getByRole('button',{name:'Use GPS for this report'}))
 expect(screen.getByRole('alert').textContent).toContain('No location was guessed');expect(fetch).not.toHaveBeenCalled()
})
it('unchanged failed submissions retain the UUID and withdrawal secret',async()=>{
 fetch.mockResolvedValueOnce({ok:false,json:async()=>({detail:'Controlled unavailable fixture'})})
 render(<CitizenReport/>);fireEvent.change(screen.getByLabelText('What did you see?'),{target:{value:'TEST ONLY flooding fixture'}});fireEvent.click(screen.getByRole('button',{name:'Use GPS for this report'}));fireEvent.click(screen.getByLabelText(/I consent to private admin review/));fireEvent.click(screen.getByRole('button',{name:'Review report'}))
 fireEvent.click(screen.getByRole('button',{name:'Submit for private review'}));await screen.findByText('Controlled unavailable fixture');fireEvent.click(screen.getByRole('button',{name:'Submit for private review'}));await screen.findByText(/Report TEST ONLY report/)
 expect(fetch.mock.calls[0][1].body).toBe(fetch.mock.calls[1][1].body)
})
it('withdraws with a secret in the body and removes private GPS from the view',async()=>{
 render(<CitizenReport/>);fireEvent.change(screen.getByLabelText('What did you see?'),{target:{value:'TEST ONLY flooding fixture'}});fireEvent.click(screen.getByRole('button',{name:'Use GPS for this report'}));fireEvent.click(screen.getByLabelText(/I consent to private admin review/));fireEvent.click(screen.getByRole('button',{name:'Review report'}));fireEvent.click(screen.getByRole('button',{name:'Submit for private review'}));await screen.findByText(/Report TEST ONLY report/)
 fetch.mockResolvedValueOnce({ok:true,json:async()=>({id:'TEST ONLY report',state:'WITHDRAWN'})});fireEvent.click(screen.getByRole('button',{name:'Withdraw private evidence'}));await screen.findByText(/Private photo and location removed/)
 expect(fetch.mock.calls[1][0]).toBe('/api/reports/TEST ONLY report/withdraw');expect(JSON.parse(fetch.mock.calls[1][1].body).withdrawal_secret).toMatch(/^[a-f0-9]{64}$/)
})
