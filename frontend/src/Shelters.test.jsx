import React from 'react'
import {afterEach,beforeEach,expect,it,vi} from 'vitest'
import {act,cleanup,fireEvent,render,screen,waitFor} from '@testing-library/react'
import PublicShelters from './PublicShelters.jsx'
import AdminShelters from './AdminShelters.jsx'
// The admin entrance map's click handler is exposed so tests can simulate a map selection.
vi.mock('./ShelterMap.jsx',()=>({default:({label,onSelect,origin})=>{if(onSelect&&label==='Administrator entrance selection map')globalThis.__adminMapSelect=onSelect;if(label==='Verified open shelter entrances'){globalThis.__shelterMapSelect=onSelect;globalThis.__shelterMapOrigin=origin};return <div role="region" aria-label={label} />}}))
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
 expect(screen.queryByRole('link',{name:/Inspect demonstration directions/})).toBeNull()
 fireEvent.click(screen.getByRole('button',{name:'Get directions'}))
 const url=new URL((await screen.findByRole('link',{name:/Inspect demonstration directions/})).href)
 expect(url.hostname).toBe('www.google.com');expect(url.searchParams.get('destination')).toBe('13.5,74.7');expect(url.searchParams.get('origin')).toBe('13.6,74.8');expect(screen.getByText(/not verified flood-safe/)).toBeTruthy()
})
it('no-location/no-shelter never invents availability',async()=>{
 fetch.mockImplementation(()=>reply(list([],'live')));render(<PublicShelters />);open();await screen.findByText('No currently verified open shelters are available in this directory.')
 expect(fetch.mock.calls[0][0]).toBe('/api/shelters');fireEvent.click(screen.getByRole('button',{name:'Limitations'}));expect(screen.getByText(/No starting location/)).toBeTruthy();fireEvent.click(screen.getByRole('button',{name:'Close'}));expect(screen.queryByRole('link',{name:/directions/})).toBeNull()
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

it.each([{kind:'network',accuracy_m:null},{kind:'gps',accuracy_m:1200,gps_timestamp:Date.now()},{kind:'gps',accuracy_m:40,gps_timestamp:0}])('does not send an uncertain/stale weather point as the routing origin',async properties=>{
 render(<PublicShelters point={{...point,...properties}} active/>);await screen.findByText(row.name)
 fireEvent.click(screen.getByRole('button',{name:'Get directions'}));await screen.findByText(/Select an adequate starting location before requesting directions. Network estimates/)
 expect(screen.queryByRole('link',{name:/directions/})).toBeNull();expect(fetch).toHaveBeenCalledTimes(1)
})
it('lists the nearest shelter first with a number and a Nearest badge, linked to the map',async()=>{
 const far={...row,id:'far',name:'DEMONSTRATION ONLY far fixture',straight_line_km:30},near={...row,id:'near',name:'DEMONSTRATION ONLY near fixture',straight_line_km:2.1,available_capacity:3}
 fetch.mockImplementation(()=>reply(list([far,near])));render(<PublicShelters point={point} active />)
 // One shelter per page (one-screen rule): nearest first, the next one after "Next".
 await screen.findByText(near.name);const card=()=>screen.getByRole('list',{name:'Available shelter destinations'}).querySelector(':scope > li')
 expect(card().querySelector('h3').textContent).toBe(near.name);expect(card().textContent).toContain('Nearest')
 expect(screen.getByText('2 open shelters with free space')).toBeTruthy()
 fireEvent.click(screen.getByRole('button',{name:'Next ›'}));expect(card().querySelector('h3').textContent).toBe(far.name);expect(card().textContent).not.toContain('Nearest')
 fireEvent.click(screen.getByRole('button',{name:'Show on map'}));expect(card().className).toContain('selected')
})
it('"Use my location" passes a timestamped GPS point to the app and never guesses on failure',async()=>{
 const onLocate=vi.fn(),position={coords:{latitude:13.34,longitude:74.74,accuracy:25},timestamp:Date.now()}
 const getCurrentPosition=vi.fn(ok=>ok(position));vi.stubGlobal('navigator',{...navigator,geolocation:{getCurrentPosition}});vi.stubGlobal('isSecureContext',true)
 render(<PublicShelters point={null} active onLocate={onLocate}/>);await screen.findByText(/Set your location to list the nearest shelters first/)
 fireEvent.click(screen.getByRole('button',{name:'Use my location'}))
 await waitFor(()=>expect(onLocate).toHaveBeenCalledWith({name:'Your GPS location',latitude:13.34,longitude:74.74,accuracy_m:25,gps_timestamp:position.timestamp,kind:'gps'}))
 getCurrentPosition.mockImplementation((ok,fail)=>fail({code:1}));onLocate.mockClear()
 fireEvent.click(screen.getByRole('button',{name:'Use my location'}));expect(await screen.findByText(/permission denied/)).toBeTruthy();expect(onLocate).not.toHaveBeenCalled()
})
it('a map click fills district, empty name and address from the place lookup, never overwriting typed text',async()=>{
 const place={status:'available',district:{name:'Udupi',aliases:['Udupi'],source:'IMD district boundary (map service)'},name:{value:'TEST FIXTURE hall',source:'OpenStreetMap'},address:{value:'TEST Road, Manipal, Udupi, Karnataka 576101',source:'OpenStreetMap'},messages:[],attribution:'Place and address suggestion: © OpenStreetMap contributors, ODbL 1.0 (via Nominatim).'}
 adminFetch();const base=fetch.getMockImplementation();fetch.mockImplementation((url,options={})=>String(url).startsWith('/api/admin/place')?reply(place):base(url,options))
 render(<AdminShelters />);await login();await waitFor(()=>expect(screen.getByRole('button',{name:'Save shelter assignment'}).disabled).toBe(false))
 fireEvent.change(screen.getByLabelText('Facility address'),{target:{value:'Typed by admin'}})
 const select=globalThis.__adminMapSelect;expect(typeof select).toBe('function');await act(async()=>{select({latitude:13.35,longitude:74.78})})
 await screen.findByText(/From the map point/)
 expect(screen.getByLabelText('Facility name').value).toBe('TEST FIXTURE hall');expect(screen.getByLabelText('Facility address').value).toBe('Typed by admin')
 expect(screen.getByLabelText('Shelter district').value).toBe('nic:udupi.nic.in');expect(screen.getByRole('button',{name:'Use this address'})).toBeTruthy()
 expect(fetch.mock.calls.some(([u])=>String(u).startsWith('/api/admin/place?latitude=13.350000&longitude=74.780000'))).toBe(true)
 expect(screen.getByRole('link',{name:'© OpenStreetMap contributors'})).toBeTruthy()
})
const gpsPoint=(accuracy=20)=>({name:'Your GPS location',latitude:13.34,longitude:74.74,accuracy_m:accuracy,gps_timestamp:Date.now(),kind:'gps'})
function stubGps(result){const getCurrentPosition=vi.fn((ok,fail)=>result?ok(result):fail({code:1}));vi.stubGlobal('navigator',{...navigator,geolocation:{getCurrentPosition}});vi.stubGlobal('isSecureContext',true);return getCurrentPosition}
it('"Get directions" without a location asks for it, then rechecks and opens directions automatically',async()=>{
 const onLocate=vi.fn();stubGps({coords:{latitude:13.34,longitude:74.74,accuracy:20},timestamp:Date.now()})
 const {rerender}=render(<PublicShelters point={null} active onLocate={onLocate}/>);await screen.findByText(row.name)
 fireEvent.click(screen.getByRole('button',{name:'Get directions'}))
 expect(screen.getByText(/Finding your location for directions/)).toBeTruthy();await waitFor(()=>expect(onLocate).toHaveBeenCalledWith(expect.objectContaining({kind:'gps',accuracy_m:20})))
 rerender(<PublicShelters point={gpsPoint()} active onLocate={onLocate}/>)
 expect(await screen.findByRole('heading',{name:'Directions to '+row.name})).toBeTruthy()
 expect(fetch.mock.calls.filter(([u])=>String(u).startsWith('/api/shelters?latitude=13.34')).length).toBeGreaterThanOrEqual(2)  // directory rechecked from the new start point
})
it('the Home "nearest open shelter" request opens directions to the nearest shelter',async()=>{
 const far={...row,id:'far',name:'DEMONSTRATION ONLY far fixture',straight_line_km:30},near={...row,id:'near',name:'DEMONSTRATION ONLY near fixture',straight_line_km:2.1}
 fetch.mockImplementation(()=>reply(list([far,near])))
 render(<PublicShelters point={gpsPoint()} active onLocate={vi.fn()} nearestRequest={1}/>)
 expect(await screen.findByRole('heading',{name:'Directions to '+near.name})).toBeTruthy()
})
it('an imprecise location never produces directions and says how to fix it',async()=>{
 const onLocate=vi.fn();stubGps({coords:{latitude:13.34,longitude:74.74,accuracy:900},timestamp:Date.now()})
 const {rerender}=render(<PublicShelters point={null} active onLocate={onLocate} nearestRequest={1}/>);await waitFor(()=>expect(onLocate).toHaveBeenCalled())
 rerender(<PublicShelters point={gpsPoint(900)} active onLocate={onLocate} nearestRequest={1}/>)
 expect(await screen.findByText(/too uncertain \(±900 m\) for directions/)).toBeTruthy();expect(screen.queryByRole('heading',{name:/^Directions to/})).toBeNull()
})
it('when GPS is refused, the start can be clicked on the shelter map and directions continue',async()=>{
 const onLocate=vi.fn();stubGps(null)
 const {rerender}=render(<PublicShelters point={null} active onLocate={onLocate}/>);await screen.findByText(row.name)
 expect(globalThis.__shelterMapSelect).toBeNull()  // map clicks do nothing until the user chooses to pick a start
 fireEvent.click(screen.getByRole('button',{name:'Get directions'}))
 fireEvent.click(await screen.findByRole('button',{name:'Choose my start on the map'}))
 expect(screen.getAllByText('Click your starting point on the map.').length).toBeGreaterThan(0)
 act(()=>{globalThis.__shelterMapSelect({latitude:13.36,longitude:74.76})})
 expect(onLocate).toHaveBeenCalledWith({name:'Start point chosen on the map',latitude:13.36,longitude:74.76,kind:'map',uncertainty_m:50})
 rerender(<PublicShelters point={{name:'Start point chosen on the map',latitude:13.36,longitude:74.76,kind:'map',uncertainty_m:50}} active onLocate={onLocate}/>)
 expect(await screen.findByRole('heading',{name:'Directions to '+row.name})).toBeTruthy()
})

// Browsers report a coarse fix first and refine it; the page keeps watching briefly for the best one.
function stubWatch(){const calls={};const clearWatch=vi.fn();const watchPosition=vi.fn((ok,fail)=>{calls.ok=ok;calls.fail=fail;return 7})
 vi.stubGlobal('navigator',{...navigator,geolocation:{watchPosition,clearWatch,getCurrentPosition:vi.fn()}});vi.stubGlobal('isSecureContext',true);return {calls,watchPosition,clearWatch}}
const fix=accuracy=>({coords:{latitude:13.34,longitude:74.74,accuracy},timestamp:Date.now()})
it('keeps the most accurate fix instead of the first coarse one, and stops once it is precise',async()=>{
 const onLocate=vi.fn(),{calls,clearWatch}=stubWatch()
 render(<PublicShelters point={null} active onLocate={onLocate}/>);await screen.findByText(/Set your location to list the nearest shelters first/)
 fireEvent.click(screen.getByRole('button',{name:'Use my location'}))
 act(()=>calls.ok(fix(850)));expect(await screen.findByRole('button',{name:'±850 m, improving…'})).toBeTruthy();expect(onLocate).not.toHaveBeenCalled()
 act(()=>calls.ok(fix(2000)));expect(screen.getByRole('button',{name:'±850 m, improving…'})).toBeTruthy()  // a worse later fix is ignored
 act(()=>calls.ok(fix(12)))
 await waitFor(()=>expect(onLocate).toHaveBeenCalledWith(expect.objectContaining({kind:'gps',accuracy_m:12})));expect(onLocate).toHaveBeenCalledOnce();expect(clearWatch).toHaveBeenCalledWith(7)
})
it('a fix still too coarse for directions is shown as an area and the exact start can be tapped on the map',async()=>{
 const onLocate=vi.fn(),{calls}=stubWatch()
 const {rerender}=render(<PublicShelters point={null} active onLocate={onLocate}/>);await screen.findByText(/Set your location to list the nearest shelters first/)
 fireEvent.click(screen.getByRole('button',{name:'Use my location'}))
 act(()=>{calls.ok(fix(900));calls.fail({code:3})})  // no better fix arrives
 await waitFor(()=>expect(onLocate).toHaveBeenCalledWith(expect.objectContaining({kind:'gps',accuracy_m:900})))
 rerender(<PublicShelters point={gpsPoint(900)} active onLocate={onLocate}/>)
 expect(screen.getByText(/located you only to ±900 m; directions need ±100 m/)).toBeTruthy()
 expect(screen.getAllByText('Click your starting point on the map.').length).toBeGreaterThan(0)
 expect(globalThis.__shelterMapOrigin).toEqual(expect.objectContaining({accuracy_m:900,showAccuracy:true}))
 act(()=>{globalThis.__shelterMapSelect({latitude:13.341,longitude:74.742})})
 expect(onLocate).toHaveBeenLastCalledWith({name:'Start point chosen on the map',latitude:13.341,longitude:74.742,kind:'map',uncertainty_m:50})
 expect(screen.queryByText('Click your starting point on the map.')).toBeNull();expect(screen.queryByRole('heading',{name:/^Directions to/})).toBeNull()
})
it('a precise but expired GPS start is refreshed once when Shelters opens',async()=>{
 const {watchPosition}=stubWatch()
 const old={...gpsPoint(30),gps_timestamp:Date.now()-6*60000}
 const {rerender}=render(<PublicShelters point={old} active onLocate={vi.fn()}/>)
 await waitFor(()=>expect(watchPosition).toHaveBeenCalledOnce())
 rerender(<PublicShelters point={old} active onLocate={vi.fn()}/>);expect(watchPosition).toHaveBeenCalledOnce()
})
