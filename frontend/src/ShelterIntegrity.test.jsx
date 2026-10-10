import React from 'react'
import {afterEach,beforeEach,expect,it,vi} from 'vitest'
import {act,cleanup,fireEvent,render,screen,waitFor} from '@testing-library/react'
import PublicShelters from './PublicShelters.jsx'
import AdminShelters from './AdminShelters.jsx'
const map=vi.hoisted(()=>vi.fn())
vi.mock('./ShelterMap.jsx',()=>({default:props=>{map(props);return <div role="region" aria-label={props.label}/>}}))
const point={name:'ISOLATED TEST origin',latitude:13.6,longitude:74.8}
const shelter=()=>({id:'isolated-test',name:'DEMONSTRATION ONLY fixture',address:'Not a real shelter',district_id:'nic:udupi.nic.in',district_name:'Udupi',latitude:13.5,longitude:74.7,capacity:10,occupancy:2,available_capacity:8,water:'yes',toilets:'unknown',accessibility:'Fixture information',status:'open',verified_at:new Date().toISOString(),updated_at:new Date().toISOString(),verification_expires_at:new Date(Date.now()+86400000).toISOString(),demonstration:true,revision:1})
const list=rows=>({status:'available',mode:'demonstration',shelters:rows,total:rows.length})
const reply=(data,status=200)=>Promise.resolve({ok:status===200,status,json:async()=>data})
beforeEach(()=>{map.mockClear();vi.stubGlobal('fetch',vi.fn(()=>reply(list([shelter()]))))})
afterEach(()=>{cleanup();vi.unstubAllGlobals();vi.useRealTimers()})
it('one-minute revalidation removes a destination closed by an administrator',async()=>{
 vi.useFakeTimers();fetch.mockImplementationOnce(()=>reply(list([shelter()]))).mockImplementation(()=>reply(list([])))
 render(<PublicShelters point={point} active/>);await act(async()=>{});expect(screen.getByText('DEMONSTRATION ONLY fixture')).toBeTruthy()
 await act(async()=>{await vi.advanceTimersByTimeAsync(59999)});expect(fetch).toHaveBeenCalledTimes(1)
 await act(async()=>{await vi.advanceTimersByTimeAsync(1)});expect(fetch).toHaveBeenCalledTimes(2);expect(screen.queryByText('DEMONSTRATION ONLY fixture')).toBeNull()
})
it('tab reactivation revalidates fresh data and an unavailable response removes directions',async()=>{
 render(<PublicShelters point={point} active/>);await screen.findByText('DEMONSTRATION ONLY fixture')
 fetch.mockImplementation(()=>reply({detail:'Controlled outage'},503));fireEvent(window,new Event('focus'));await screen.findByText(/Controlled outage/)
 expect(screen.queryByRole('link',{name:/directions/})).toBeNull();expect(fetch).toHaveBeenCalledTimes(2)
 fireEvent(window,new Event('focus'));fireEvent(document,new Event('visibilitychange'));expect(fetch).toHaveBeenCalledTimes(2)
})
it('hidden routes stop polling and returning to the page revalidates',async()=>{
 vi.useFakeTimers();const {rerender,unmount}=render(<PublicShelters point={point} active/>);await act(async()=>{})
 rerender(<PublicShelters point={point} active={false}/>);await act(async()=>{await vi.advanceTimersByTimeAsync(120000)})
 expect(fetch).toHaveBeenCalledTimes(1);rerender(<PublicShelters point={point} active/>);await act(async()=>{})
 expect(fetch).toHaveBeenCalledTimes(2);unmount();expect(vi.getTimerCount()).toBe(0)
})
it('directions are prevented when the latest directory no longer includes that entrance',async()=>{
 render(<PublicShelters point={point} active/>);await screen.findByText('DEMONSTRATION ONLY fixture')
 fetch.mockImplementation(()=>reply(list([])));fireEvent.click(screen.getByRole('button',{name:'Recheck availability for directions'}));await screen.findByText(/destination could not be revalidated/)
 expect(screen.queryByRole('link',{name:/directions/})).toBeNull()
})
it('successful directions revalidation requires a second explicit navigation action',async()=>{
 render(<PublicShelters point={point} active/>);await screen.findByText('DEMONSTRATION ONLY fixture')
 expect(screen.queryByRole('link',{name:/Inspect demonstration directions/})).toBeNull()
 fireEvent.click(screen.getByRole('button',{name:'Recheck availability for directions'}))
 await screen.findByText(/Availability rechecked/);expect(fetch).toHaveBeenCalledTimes(2)
 const link=screen.getByRole('link',{name:/Inspect demonstration directions/});expect(new URL(link.href).searchParams.get('destination')).toBe('13.5,74.7')
})
it('navigation permission expires after five seconds and cannot be reused',async()=>{
 vi.useFakeTimers();render(<PublicShelters point={point} active/>);await act(async()=>{})
 fireEvent.click(screen.getByRole('button',{name:'Recheck availability for directions'}));await act(async()=>{})
 expect(screen.getByRole('link',{name:/Inspect demonstration directions/})).toBeTruthy()
 await act(async()=>{await vi.advanceTimersByTimeAsync(5000)})
 expect(screen.queryByRole('link',{name:/directions/})).toBeNull();expect(screen.getByRole('button',{name:'Recheck availability for directions'})).toBeTruthy()
})
it('uncooperative directory requests time out without fabricated destinations or retry loops',async()=>{
 vi.useFakeTimers();fetch.mockImplementation(()=>new Promise(()=>{}));const {unmount}=render(<PublicShelters active/>)
 await act(async()=>{await vi.advanceTimersByTimeAsync(15000)})
 expect(screen.getByText(/request timed out/)).toBeTruthy();expect(screen.queryByRole('link',{name:/directions/})).toBeNull()
 await act(async()=>{await vi.advanceTimersByTimeAsync(60000)});expect(fetch).toHaveBeenCalledTimes(1);unmount();expect(vi.getTimerCount()).toBe(0)
})
const session={user:{id:'isolated-admin',username:'test-admin'},csrf_token:'TEST_ONLY_CSRF',mode:'demonstration'}
async function editor(){
 fetch.mockImplementation((url,options={})=>{
  if(url==='/api/admin/session')return reply(session)
  if(url==='/api/locations/districts')return reply({status:'available',items:[{id:'nic:udupi.nic.in',name:'Udupi'},{id:'nic:dk.nic.in',name:'ISOLATED district'}]})
  if(url.startsWith('/api/admin/shelters'))return reply({shelters:[shelter()],total:1})
  if(url==='/api/admin/notifications/options')return reply({configured:false,destinations:[],shelters:[]})
  if(url.startsWith('/api/admin/notifications'))return reply({notifications:[],total:0})
  if(url==='/api/admin/logout')return reply({status:'logged_out'})
  throw Error('Unexpected isolated request')
 })
 render(<AdminShelters/>);await screen.findByRole('button',{name:'Edit DEMONSTRATION ONLY fixture'});fireEvent.click(screen.getByRole('button',{name:'Edit DEMONSTRATION ONLY fixture'}))
 for(const label of ['Facility is authorized for shelter use','This exact entrance has been independently verified','Facility is currently usable','Capacity and current occupancy have been checked'])fireEvent.click(screen.getByLabelText(label))
 fireEvent.change(screen.getByLabelText('Verification evidence and method'),{target:{value:'ISOLATED TEST evidence'}})
}
it.each([['Facility name','Changed name'],['Facility address','Changed address'],['Shelter district','nic:dk.nic.in'],['Entrance latitude','13.51'],['Entrance longitude','74.71'],['Maximum capacity','11'],['Current occupancy','3'],['Water availability','no'],['Toilets','yes'],['Accessibility information','Changed'],['Public operational restrictions','Changed']])('material edit to %s invalidates earlier confirmations',async(label,value)=>{
 await editor();fireEvent.change(screen.getByLabelText(label),{target:{value}})
 for(const box of screen.getAllByRole('checkbox').filter(e=>e.closest('fieldset')))expect(box.checked).toBe(false)
 expect(screen.getByLabelText('Verification evidence and method').value).toBe('')
})
it('internal note edits preserve confirmations and do not recenter the entrance map',async()=>{
 await editor();const points=map.mock.calls.at(-1)[0].points
 fireEvent.change(screen.getByLabelText('Internal notes (not public)'),{target:{value:'ISOLATED PRIVATE TEST note'}})
 expect(screen.getByLabelText('This exact entrance has been independently verified').checked).toBe(true)
 expect(map.mock.calls.at(-1)[0].points).toBe(points)
})
it('logout clears the private editor and a late list cannot repopulate it',async()=>{
 await editor();const normal=fetch.getMockImplementation();let finish
 fetch.mockImplementation((url,options)=>url.startsWith('/api/admin/shelters')?new Promise(resolve=>{finish=resolve}):normal(url,options))
 fireEvent.click(screen.getByRole('button',{name:'Refresh assignments'}));await waitFor(()=>expect(finish).toBeTruthy())
 fireEvent.click(screen.getByRole('button',{name:'Sign out'}));await screen.findByRole('button',{name:'Sign in'})
 await act(async()=>finish({ok:true,status:200,json:async()=>({shelters:[shelter()],total:1})}))
 expect(screen.queryByLabelText('Facility name')).toBeNull();expect(screen.getByLabelText('Password').value).toBe('')
})
it('expired sessions clear the private editor and return to login',async()=>{
 await editor();fetch.mockImplementation(()=>reply({detail:'Session expired'},401))
 fireEvent.click(screen.getByRole('button',{name:'Refresh assignments'}));await screen.findByRole('button',{name:'Sign in'})
 expect(screen.queryByLabelText('Facility name')).toBeNull();expect(screen.queryByText(/Signed in as/)).toBeNull();expect(screen.getByLabelText('Username').value).toBe('')
})
it('logout hides private information immediately even if the server response is lost',async()=>{
 await editor();const normal=fetch.getMockImplementation();fetch.mockImplementation((url,options)=>url==='/api/admin/logout'?reply({detail:'Controlled network outage'},503):normal(url,options))
 fireEvent.click(screen.getByRole('button',{name:'Sign out'}));expect(screen.queryByLabelText('Facility name')).toBeNull()
 await screen.findByText('Controlled network outage');expect(screen.queryByText(/Signed in as/)).toBeNull();expect(screen.getByLabelText('Password').value).toBe('')
})

it('split directory and map share one fresh response and district filtering cannot fabricate destinations',async()=>{
 const target=document.createElement('section');target.setAttribute('aria-label','ISOLATED map panel');document.body.append(target)
 const {rerender,unmount}=render(<PublicShelters point={point} active mapTarget={target} districtId="nic:udupi.nic.in"/>)
 await screen.findByText('DEMONSTRATION ONLY fixture')
 expect(target.querySelector('[role=region]')).toBeTruthy();expect(fetch).toHaveBeenCalledTimes(1)
 expect(map.mock.calls.at(-1)[0].points).toHaveLength(1)
 rerender(<PublicShelters point={point} active mapTarget={target} districtId="nic:dk.nic.in"/>)
 expect(screen.queryByText('DEMONSTRATION ONLY fixture')).toBeNull()
 expect(map.mock.calls.at(-1)[0].points).toHaveLength(0);expect(fetch).toHaveBeenCalledTimes(1)
 unmount();target.remove()
})
