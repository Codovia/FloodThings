import React from 'react'
import {render,screen,fireEvent,cleanup,waitFor} from '@testing-library/react'
import {it,expect,vi,afterEach} from 'vitest'
import AdminReports from './AdminReports.jsx'
vi.mock('./ShelterMap.jsx',()=>({default:()=> <div>DEMO ONLY map fixture</div>}))
afterEach(cleanup)
it('prioritizes report evidence, discloses technical metadata and preserves explicit review transitions',async()=>{
 let report={id:'demo-only',event_type:'flooding',state:'SUBMITTED',revision:1,description:'DEMO ONLY — invented incident for isolated component testing.',received_at:new Date().toISOString(),observed_at:new Date().toISOString(),latitude:13.4,longitude:74.7,accuracy_m:250,position_source:'USER_SELECTED_MAP',accuracy_kind:'USER_ESTIMATED',image_sha256:'a'.repeat(64),image_metadata:{format:'PNG',width:2,height:2,vision_model:'unavailable'}}
 const request=vi.fn(async(path,options={})=>{
  if(options.method==='POST'){const body=JSON.parse(options.body);report={...report,state:body.state,revision:report.revision+1};return report}
  return {mode:'demonstration',reports:[report],total:1}
 })
 render(<AdminReports request={request} active/> )
 fireEvent.click(await screen.findByRole('button',{name:'flooding · SUBMITTED'}))
 expect(document.activeElement).toBe(screen.getByRole('heading',{name:'Report evidence'}))
 const details=screen.getByText('Image metadata and provenance').closest('details')
 expect(details.open).toBe(false)
 expect(screen.getByRole('button',{name:'Start review'}).disabled).toBe(true)
 fireEvent.change(screen.getByLabelText('Review reason and evidence (avoid personal identifiers)'),{target:{value:'DEMO ONLY — inspected fixture; no flood certification.'}})
 fireEvent.click(screen.getByRole('button',{name:'Start review'}))
 await screen.findByRole('button',{name:'flooding · UNDER_REVIEW'})
 expect(JSON.parse(request.mock.calls.find(([,options])=>options?.method==='POST')[1].body)).toMatchObject({state:'UNDER_REVIEW',revision:1})
 fireEvent.click(screen.getByRole('button',{name:'Reject report'}))
 await waitFor(()=>expect(screen.getByRole('button',{name:'flooding · REJECTED'})).toBeTruthy())
 expect(screen.queryByRole('button',{name:'Reject report'})).toBeNull()
 expect(screen.getByText(/does not certify a flood/)).toBeTruthy()
 expect(screen.getByText('Retention maintenance').closest('details').open).toBe(false)
})
it('shows in-app GPS camera capture details and the IMD district in plain words',async()=>{
 const {default:AdminReports}=await import('./AdminReports.jsx')
 const report={id:'cap1',event_type:'flooding',state:'SUBMITTED',received_at:'2026-10-18T06:00:30Z',observed_at:'2026-10-18T06:00:00Z',description:'TEST FIXTURE GPS camera report',latitude:13.34,longitude:74.74,accuracy_m:12,accuracy_kind:'BROWSER_REPORTED',position_source:'BROWSER_GPS',revision:1,image_metadata:{format:'JPEG',width:1920,height:1080,vision_model:'unavailable',flags:[],capture:{source:'IN_APP_GPS_CAMERA',client_reported:true,captured_at:'2026-10-18T06:00:00Z',gps_fix_at:'2026-10-18T05:59:56Z',gps_fix_gap_s:4,gps_accuracy_m:12,flags:[]},district:{name:'Udupi',source:'IMD district boundary (map service)'}}}
 const request=vi.fn(async()=>({reports:[report],total:1,mode:'live'}))
 render(<AdminReports request={request} active/>)
 fireEvent.click(await screen.findByRole('button',{name:'flooding · SUBMITTED'}))
 expect(screen.getByText(/In-app GPS camera photo/).closest('p').textContent).toMatch(/GPS ±12 m, fix 4 s from the photo · no timing flags/)
 expect(screen.getByText(/District: Udupi \(IMD district boundary/)).toBeTruthy()
})
