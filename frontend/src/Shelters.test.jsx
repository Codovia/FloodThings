import React from 'react'
import {afterEach,beforeEach,expect,it,vi} from 'vitest'
import {act,cleanup,fireEvent,render,screen,waitFor} from '@testing-library/react'
import PublicShelters from './PublicShelters.jsx'
import AdminShelters from './AdminShelters.jsx'
vi.mock('./ShelterMap.jsx',()=>({default:({label})=><div role="region" aria-label={label} />}))
const point={name:'Test origin',latitude:13.6,longitude:74.8}
const row={id:'isolated-test',name:'DEMONSTRATION ONLY fixture',address:'Never a real shelter',district_id:'nic:udupi.nic.in',district_name:'Udupi',latitude:13.5,longitude:74.7,capacity:10,occupancy:2,available_capacity:8,water:'yes',toilets:'unknown',accessibility:'Fixture information',status:'open',verified_at:new Date().toISOString(),updated_at:new Date().toISOString(),verification_expires_at:new Date(Date.now()+86400000).toISOString(),demonstration:true,straight_line_km:12.4,restrictions:'DO NOT TRAVEL',contact:null}
const list=(rows=[row],mode='demonstration')=>({status:'available',mode,shelters:rows,total:rows.length,verification_valid_hours:24})
const reply=(data,ok=true,status=ok?200:503)=>Promise.resolve({ok,status,json:async()=>data})
const open=()=>fireEvent.click(screen.getByRole('button',{name:'Find open shelters'}))
beforeEach(()=>vi.stubGlobal('fetch',vi.fn(()=>reply(list()))))
afterEach(()=>{cleanup();vi.unstubAllGlobals();vi.useRealTimers()})
it('loads on demand and encodes exact entrance while announcing demonstration and route limitations',async()=>{
 render(<PublicShelters point={point} />);expect(fetch).not.toHaveBeenCalled();open();await screen.findByText(row.name)
 expect(screen.getByText(/DEMONSTRATION ONLY — isolated test assignments/)).toBeTruthy()
 expect(screen.getByText(/8 available/)).toBeTruthy();expect(screen.getByText(/12.4 km approximate straight-line/)).toBeTruthy()
 const url=new URL(screen.getByRole('link',{name:/Inspect demonstration directions/}).href)
 expect(url.hostname).toBe('www.google.com');expect(url.searchParams.get('destination')).toBe('13.5,74.7');expect(url.searchParams.get('origin')).toBe('13.6,74.8');expect(screen.getByText(/not verified flood-safe/)).toBeTruthy()
})
it('no-location/no-shelter never invents availability',async()=>{
 fetch.mockImplementation(()=>reply(list([],'live')));render(<PublicShelters />);open();await screen.findByText('No currently verified open shelters are available in this directory.')
 expect(fetch.mock.calls[0][0]).toBe('/api/shelters');expect(screen.getByText(/No starting location/)).toBeTruthy();expect(screen.queryByRole('link',{name:/directions/})).toBeNull()
})
it.each(['pending','full','closed','expired','unverified','demo-conflict'])('rejects unavailable destination: %s',async(kind)=>{
 const r={...row};if(['pending','full','closed'].includes(kind))r.status=kind
 if(kind==='expired')r.verification_expires_at='2020-01-01T00:00:00Z'
 if(kind==='unverified')r.verified_at=null
 if(kind==='demo-conflict')r.demonstration=false
 fetch.mockImplementation(()=>reply(list([r])));render(<PublicShelters point={point} />);open();await screen.findByText(/Shelter availability could not be verified/);expect(screen.queryByRole('link',{name:/directions/})).toBeNull()
})
it('directory outage clears previous destinations',async()=>{
 render(<PublicShelters point={point} />);open();await screen.findByText(row.name)
 fetch.mockImplementation(()=>reply({detail:'Controlled database outage'},false));fireEvent.click(screen.getByRole('button',{name:'Refresh shelters'}));await screen.findByText(/Controlled database outage/);expect(screen.queryByText(row.name)).toBeNull()
})
it('location switching cancels and suppresses a late result',async()=>{
 let finish;fetch.mockImplementationOnce(()=>new Promise(resolve=>{finish=resolve})).mockImplementation(()=>reply(list([],'live')))
 const {rerender}=render(<PublicShelters point={point} />);open();const signal=fetch.mock.calls[0][1].signal;rerender(<PublicShelters point={{name:'New',latitude:12,longitude:75}} />)
 await screen.findByText('No currently verified open shelters are available in this directory.');await act(async()=>finish({ok:true,json:async()=>list()}));expect(signal.aborted).toBe(true);expect(screen.queryByText(row.name)).toBeNull()
})
it('verification expiration removes stale availability',async()=>{
 vi.useFakeTimers();const expires=new Date(Date.now()+1000).toISOString();fetch.mockImplementationOnce(()=>reply(list([{...row,verification_expires_at:expires}]))).mockImplementation(()=>reply(list([],'live')))
 render(<PublicShelters point={point} />);open();await act(async()=>{});expect(screen.getByText(row.name)).toBeTruthy();await act(async()=>{await vi.advanceTimersByTimeAsync(1050)})
 expect(screen.getByText('No currently verified open shelters are available in this directory.')).toBeTruthy();expect(fetch).toHaveBeenCalledTimes(2)
})
it('timeout and unmount clean up without automatic retry loops',async()=>{
 vi.useFakeTimers();fetch.mockImplementation((url,{signal})=>new Promise((resolve,reject)=>signal.addEventListener('abort',()=>reject(new DOMException('Aborted','AbortError')))))
 const {unmount}=render(<PublicShelters point={point} />);open();await act(async()=>{await vi.advanceTimersByTimeAsync(15000)});expect(screen.getByText(/timed out/)).toBeTruthy();await act(async()=>{await vi.advanceTimersByTimeAsync(60000)});expect(fetch).toHaveBeenCalledTimes(1);unmount();expect(vi.getTimerCount()).toBe(0)
})
const session={user:{id:'test-admin',username:'test-admin'},csrf_token:'TEST_ONLY_CSRF',mode:'demonstration'}
function adminFetch(){fetch.mockImplementation((url,options={})=>{
 if(url==='/api/admin/session')return reply({},false,401)
 if(url==='/api/admin/login')return reply(session)
 if(url==='/api/locations/districts')return reply({status:'available',items:[{id:'nic:udupi.nic.in',name:'Udupi'}],total:1})
 if(url.startsWith('/api/admin/shelters')&&options.method==='POST')return reply({...row,status:'pending',revision:1,publicly_available:false})
 if(url.startsWith('/api/admin/shelters'))return reply({shelters:[],total:0})
 if(url==='/api/admin/logout')return reply({status:'logged_out'})
 throw Error('Unexpected request')
})}
async function login(){await screen.findByRole('button',{name:'Sign in'});fireEvent.change(screen.getByLabelText('Username'),{target:{value:'test-admin'}});fireEvent.change(screen.getByLabelText('Password'),{target:{value:'ISOLATED TEST PASSWORD ONLY'}});fireEvent.click(screen.getByRole('button',{name:'Sign in'}));await screen.findByText(/Signed in as test-admin/)}
it('separate admin login protects Pending creation, CSRF and logout',async()=>{
 adminFetch();render(<AdminShelters />);await login();await waitFor(()=>expect(screen.getByRole('button',{name:'Save shelter assignment'}).disabled).toBe(false));expect(screen.getByText(/DEMONSTRATION ONLY — isolated database/)).toBeTruthy()
 for(const [label,value] of [['Facility name','DEMONSTRATION ONLY fixture'],['Facility address','Not a shelter'],['Shelter district','nic:udupi.nic.in'],['Maximum capacity','10'],['Current occupancy','2']])fireEvent.change(screen.getByLabelText(label),{target:{value}})
 expect(screen.getByLabelText('Shelter status').disabled).toBe(true);fireEvent.submit(screen.getByRole('form',{name:'Shelter assignment form'}));await screen.findByText(/Assignment saved/)
 const [,options]=fetch.mock.calls.find(([u,o])=>u==='/api/admin/shelters'&&o.method==='POST');const body=JSON.parse(options.body)
 expect(body.status).toBe('pending');expect(body.latitude).toBeNull();expect(body.verification.authorization).toBe(false);expect(options.headers['X-CSRF-Token']).toBe('TEST_ONLY_CSRF')
 fireEvent.click(screen.getByRole('button',{name:'Sign out'}));await screen.findByRole('button',{name:'Sign in'});expect(screen.getByLabelText('Password').value).toBe('')
})
it('failed login clears the password and displays a generic error',async()=>{
 fetch.mockImplementation(url=>url==='/api/admin/session'?reply({},false,401):reply({detail:'Invalid administrator credentials'},false,401));render(<AdminShelters />);await screen.findByRole('button',{name:'Sign in'});fireEvent.change(screen.getByLabelText('Username'),{target:{value:'test-admin'}});fireEvent.change(screen.getByLabelText('Password'),{target:{value:'WRONG TEST PASSWORD'}});fireEvent.click(screen.getByRole('button',{name:'Sign in'}));await screen.findByText('Invalid administrator credentials');expect(screen.getByLabelText('Password').value).toBe('')
})

it('malformed district contract stays an explicit error rather than crashing or enabling assignment',async()=>{
 adminFetch();const normal=fetch.getMockImplementation();fetch.mockImplementation((url,options)=>url==='/api/locations/districts'?reply({districts:[]}):normal(url,options));render(<AdminShelters />);await login();await screen.findByText('Location directory or shelter response unavailable');expect(screen.getByRole('button',{name:'Save shelter assignment'}).disabled).toBe(true)
})
