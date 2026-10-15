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
