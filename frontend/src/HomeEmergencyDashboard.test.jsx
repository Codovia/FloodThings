import React from 'react'
import {act,cleanup,fireEvent,render,screen,waitFor} from '@testing-library/react'
import {afterEach,beforeEach,expect,it,vi} from 'vitest'
import HomeEmergencyDashboard from './HomeEmergencyDashboard.jsx'
const settle=()=>act(async()=>{for(let i=0;i<10;i++)await new Promise(r=>setTimeout(r,0))})
const mapProps=vi.hoisted(()=>({current:null}))
vi.mock('./HomeFloodMap.jsx',()=>({default:props=>{mapProps.current=props;return <div>Home map fixture</div>}}))
vi.mock('./LocationDirectorySelector.jsx',()=>({default:({onChoose,onDistrict})=><><button onClick={()=>onChoose({name:'Verified fixture locality',latitude:13.4,longitude:74.7,locality_id:'test-only'})}>Choose fixture locality</button><button onClick={()=>onDistrict({id:'test-district',name:'Fixture district'})}>Choose district only</button></>}))
const point={name:'GPS-selected point',latitude:13.4,longitude:74.7,accuracy_m:40,kind:'gps'}
const props=()=>({point,session:{data:{retrieved_at:new Date().toISOString(),current:{valid_at:new Date().toISOString(),temperature_c:27,precipitation_mm:1,interval_seconds:900},forecast:[]},freshness:'fresh',loading:false,error:null,refresh:vi.fn()},location:{message:'GPS test receipt',status:'inside',request:vi.fn()},choosePoint:vi.fn(),chooseDistrict:vi.fn(),navigate:vi.fn()})
const unsupported={status:'unsupported',message:'No verified association.'}
beforeEach(()=>vi.stubGlobal('fetch',vi.fn(async()=>({ok:true,json:async()=>unsupported}))))
afterEach(()=>{cleanup();vi.unstubAllGlobals();vi.useRealTimers()})
it('shows weather and exact unavailable flood wording while removing Home historical/shelter calls and content',async()=>{
 render(<HomeEmergencyDashboard {...props()}/>);await settle()
 expect(screen.getByRole('heading',{name:'27 °C'})).toBeTruthy();expect(screen.getByText(/At your location: unavailable/)).toBeTruthy();expect(screen.getByLabelText('Current weather and rain').textContent).toContain('Unavailable rain forecast in the next 24 h')
 expect(screen.queryByText(/Verified Open shelters|56 reviewed/)).toBeNull();expect(screen.queryByRole('button',{name:'Refresh shelters'})).toBeNull()
 expect(screen.getByRole('link',{name:'Historical flood evidence'}).getAttribute('href')).toBe('/flood-map');expect(screen.getByRole('link',{name:'Report flooding or blocked drainage'})).toBeTruthy()
 expect(fetch.mock.calls.map(([u])=>u.split('?')[0]).sort()).toEqual(['/api/official/districts','/api/official/warnings','/api/risk','/api/risk/area']);expect(mapProps.current.river).toBeUndefined();expect(screen.queryByText(/Reviewed river outlook/)).toBeNull();expect(mapProps.current.features).toBeUndefined();expect(mapProps.current.shelters).toBeUndefined()
})
it('district-only fallback cannot display cached default weather or invent a point',async()=>{
 const p=props();render(<HomeEmergencyDashboard {...p} point={null} districtId="fixture" district={{name:'Fixture district'}}/>);
 expect(screen.queryByRole('heading',{name:'27 °C'})).toBeNull();expect(mapProps.current.point).toBeNull();expect(fetch.mock.calls.map(([u])=>u).sort()).toEqual(['/api/official/districts','/api/official/warnings'])
 fireEvent.click(screen.getByText('Choose district only'));expect(p.chooseDistrict).toHaveBeenCalledWith({id:'test-district',name:'Fixture district'})
 fireEvent.click(screen.getByText('Choose fixture locality'));expect(p.choosePoint).toHaveBeenCalledWith(expect.objectContaining({locality_id:'test-only'}))
})
it.each(['loading','failure','stale'])('shows explicit %s weather without a current estimate',async kind=>{
 const p=props();p.session={...p.session,loading:kind==='loading',error:kind==='failure'?'Controlled provider failure':null,freshness:kind==='loading'?'refreshing':kind==='failure'?'unavailable':'stale'}
 render(<HomeEmergencyDashboard {...p}/>);await settle()
 expect(screen.queryByRole('heading',{name:'27 °C'})).toBeNull();expect(screen.getByRole('heading',{name:kind==='loading'?'Loading weather…':'Current weather unavailable'})).toBeTruthy()
 if(kind==='failure')expect(screen.getByRole('alert').textContent).toContain('Controlled provider failure')
})
it('coarse fallback is prominent and requests neither weather nor river for an unaccepted point',()=>{
 render(<HomeEmergencyDashboard {...props()} point={null} location={{message:'Accuracy too large',status:'coarse'}}/>);
 expect(screen.getByRole('heading',{name:'Approximate location — select your town'})).toBeTruthy();expect(screen.getByRole('heading',{name:'Local Conditions & Flood Outlook'})).toBeTruthy();expect(screen.getAllByText(/official IMD and NDMA warnings|Official warnings could not be checked/).length).toBeGreaterThan(0);expect(fetch.mock.calls.map(([u])=>u).sort()).toEqual(['/api/official/districts','/api/official/warnings'])
})
it('shows WMO current conditions, optional fields and a complete hourly total without flood inference',async()=>{
 const p=props(),begin=Math.ceil((Date.now()+19800000)/3600000)*3600000-19800000
 p.session.data.current={...p.session.data.current,weather_code:61,humidity_percent:70,wind_speed:12,wind_speed_unit:'km/h'}
 p.session.data.hourly_precipitation={status:'available',timezone:'Asia/Kolkata',unit:'mm',interval_seconds:3600,interval_semantics:'preceding_hour',source:{name:'Open-Meteo'},intervals:Array.from({length:24},(_,i)=>({start:new Date(begin+i*3600000).toISOString(),end:new Date(begin+(i+1)*3600000).toISOString(),precipitation_mm:.5,unit:'mm'}))}
 render(<HomeEmergencyDashboard {...p}/>);await settle()
 expect(screen.getByLabelText('Current weather and rain').textContent).toContain('12 mm rain forecast in the next 24 h');expect(screen.getByText(/Humidity: 70%\. Wind: 12 km\/h/)).toBeTruthy();expect(screen.getAllByText(/Slight rain/)).toHaveLength(1)
 expect(screen.getByText(/At your location: unavailable/)).toBeTruthy();expect(fetch).toHaveBeenCalledTimes(4);expect(fetch.mock.calls.some(([u])=>u.startsWith('/api/risk?'))).toBe(true)
})
it('missing temperature preserves other valid current fields',async()=>{
 const p=props();p.session.data.current.temperature_c=null;p.session.data.current.humidity_percent=70
 render(<HomeEmergencyDashboard {...p}/>);await settle()
 expect(screen.getByRole('heading',{name:'Temperature unavailable'})).toBeTruthy();expect(screen.getByText(/Humidity: 70%/)).toBeTruthy()
})
it('highlights the official IMD, SACHET and 24 h prediction cards and passes districts to the map',async()=>{
 render(<HomeEmergencyDashboard {...props()}/>);await settle()
 for(const name of [/Official IMD warning/,'NDMA SACHET alerts · Karnataka','Flood & drainage risk · next 24 h'])expect(screen.getByRole('heading',{name})).toBeTruthy()
 expect(screen.queryByRole('table')).toBeNull();expect(screen.queryByRole('heading',{name:'Seven-day forecast'})).toBeNull()
 expect(mapProps.current).toHaveProperty('districts');expect(mapProps.current.kind).toBe('flood');mapProps.current.onKind('drainage')
 await waitFor(()=>expect(mapProps.current.kind).toBe('drainage'))
})
