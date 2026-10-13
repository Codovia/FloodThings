import React from 'react'
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import HomeEmergencyDashboard from './HomeEmergencyDashboard.jsx'
const mapProps = vi.hoisted(() => ({ current:null }))
vi.mock('./HomeFloodMap.jsx', () => ({ default: props => { mapProps.current=props; return <div>Home map fixture</div> } }))
vi.mock('./LocationDirectorySelector.jsx', () => ({ default: ({ onChoose, onDistrict }) => <><button onClick={() => onChoose({ name:'Verified fixture locality',latitude:13.4,longitude:74.7,locality_id:'test-only' })}>Choose fixture locality</button><button onClick={() => onDistrict({ id:'test-district', name:'Fixture district' })}>Choose district only</button></> }))
const point={ name:'GPS-selected point',latitude:13.4,longitude:74.7,kind:'gps' }
const session=()=>({ data:{ retrieved_at:new Date().toISOString(),current:{ valid_at:new Date().toISOString(),temperature_c:27,precipitation_mm:1,interval_seconds:900 },forecast:[] },freshness:'fresh',loading:false,error:null,refresh:vi.fn() })
const props=()=>({ point,session:session(),overview:{ data:{ total:0,geojson:{type:'FeatureCollection',features:[]} } }, location:{message:'GPS verified test receipt',status:'inside',gps:point,request:vi.fn()},choosePoint:vi.fn(),chooseDistrict:vi.fn(),navigate:vi.fn(),onEvidence:vi.fn() })
const shelter=()=>({ id:'isolated-test',name:'ISOLATED TEST shelter',status:'open',available_capacity:4,latitude:13.3,longitude:74.8,verified_at:new Date().toISOString(),verification_expires_at:new Date(Date.now()+5000).toISOString(),demonstration:false,straight_line_km:2 })
beforeEach(() => vi.stubGlobal('fetch',vi.fn(async()=>({ ok:true,json:async()=>({status:'available',mode:'live',shelters:[]}) }))))
afterEach(() => { cleanup();vi.unstubAllGlobals();vi.useRealTimers() })
it('uses actual point weather, retains exact unavailable flood wording and no experimental inference',async()=>{
 render(<HomeEmergencyDashboard {...props()}/>);await screen.findByText('No currently verified open shelters are available in this directory.')
 expect(screen.getByRole('heading',{name:'27 °C'})).toBeTruthy();expect(screen.getByText('Validated flood forecast unavailable for this location.')).toBeTruthy()
 expect(screen.getByText('Next-24-hour total unavailable')).toBeTruthy();expect(screen.queryByText('Run experimental rainfall model')).toBeNull()
 expect(fetch.mock.calls.map(([u])=>u)).toEqual(['/api/shelters?latitude=13.4&longitude=74.7'])
})
it('district-only fallback does not display default cached weather or invent a marker',async()=>{
 const p=props();render(<HomeEmergencyDashboard {...p} point={null} districtId="fixture" district={{name:'Fixture district'}} location={{...p.location,gps:null}}/>);await screen.findByText('No currently verified open shelters are available in this directory.')
 expect(screen.queryByRole('heading',{name:'27 °C'})).toBeNull();expect(mapProps.current.point).toBeNull();expect(mapProps.current.gps).toBeNull()
 expect(fetch.mock.calls[0][0]).toBe('/api/shelters')
 fireEvent.click(screen.getByText('Choose district only'));expect(p.chooseDistrict).toHaveBeenCalledWith({id:'test-district',name:'Fixture district'})
 fireEvent.click(screen.getByText('Choose fixture locality'));expect(p.choosePoint).toHaveBeenCalledWith(expect.objectContaining({locality_id:'test-only'}))
})
it.each(['loading','failure','stale'])('shows explicit %s weather without a current estimate',async kind=>{
 const p=props();p.session={...p.session,loading:kind==='loading',error:kind==='failure'?'Controlled provider failure':null,freshness:kind==='loading'?'refreshing':kind==='failure'?'unavailable':'stale'}
 render(<HomeEmergencyDashboard {...p}/>);await screen.findByText('No currently verified open shelters are available in this directory.')
 expect(screen.queryByRole('heading',{name:'27 °C'})).toBeNull();expect(screen.getByRole('heading',{name:kind==='loading'?'Loading weather…':'Current weather unavailable.'})).toBeTruthy()
 if(kind==='failure')expect(screen.getByRole('alert').textContent).toContain('Controlled provider failure')
})
it('one live shelter receipt feeds list and map; expiry removes both during revalidation',async()=>{
 vi.useFakeTimers();const s=shelter();let finish
 fetch.mockResolvedValueOnce({ok:true,json:async()=>({status:'available',mode:'live',shelters:[s]})}).mockImplementation(()=>new Promise(resolve=>{finish=resolve}))
 render(<HomeEmergencyDashboard {...props()}/>);await act(async()=>{await vi.advanceTimersByTimeAsync(0)})
 expect(screen.getByText(s.name)).toBeTruthy();expect(mapProps.current.shelters).toEqual([s]);expect(fetch).toHaveBeenCalledTimes(1)
 await act(async()=>{await vi.advanceTimersByTimeAsync(5000)})
 expect(mapProps.current.shelters).toEqual([]);expect(screen.queryByText(s.name)).toBeNull();expect(fetch).toHaveBeenCalledTimes(2)
 await act(async()=>finish({ok:false,json:async()=>({detail:'Controlled shelter outage'})}))
 expect(screen.getByRole('alert').textContent).toContain('Controlled shelter outage');expect(mapProps.current.shelters).toEqual([])
})
it('demonstration destinations and unsupported historical geometry never become emergency markers',async()=>{
 const s={...shelter(),demonstration:true};fetch.mockResolvedValue({ok:true,json:async()=>({status:'available',mode:'demonstration',shelters:[s]})})
 const p=props();p.overview.data={total:1,geojson:{features:[{type:'Feature',geometry:{type:'Point',coordinates:[74,13]},properties:{category:'predicted_flood'}}]}}
 render(<HomeEmergencyDashboard {...p}/>);await waitFor(()=>expect(screen.getByRole('alert').textContent).toContain('DEMONSTRATION ONLY'))
 expect(mapProps.current.shelters).toEqual([]);expect(mapProps.current.features).toEqual([]);expect(screen.queryByText(s.name)).toBeNull()
})
it('district filtering preserves actual GPS point and offers existing detail routes',async()=>{
 const s=shelter();fetch.mockResolvedValue({ok:true,json:async()=>({status:'available',mode:'live',shelters:[{...s,district_id:'other'}]})})
 const p=props();render(<HomeEmergencyDashboard {...p} districtId="selected"/>);await screen.findByText('No currently verified open shelters are available in this directory.')
 expect(mapProps.current.point).toEqual(point);expect(mapProps.current.shelters).toEqual([])
 fireEvent.click(screen.getByText('View shelter details and recheck directions'));expect(p.navigate).toHaveBeenCalledWith('/shelters')
 fireEvent.click(screen.getByText('Inspect sources and historical evidence'));expect(p.navigate).toHaveBeenCalledWith('/flood-map')
})
it('shows WMO current conditions, optional fields and a full-hour total without flood inference',async()=>{
 const p=props(),begin=Math.ceil((Date.now()+19800000)/3600000)*3600000-19800000
 p.session.data.current={...p.session.data.current,weather_code:61,humidity_percent:70,wind_speed:12,wind_speed_unit:'km/h'}
 p.session.data.hourly_precipitation={status:'available',timezone:'Asia/Kolkata',unit:'mm',interval_seconds:3600,interval_semantics:'preceding_hour',source:{name:'Open-Meteo'},intervals:Array.from({length:24},(_,i)=>({start:new Date(begin+i*3600000).toISOString(),end:new Date(begin+(i+1)*3600000).toISOString(),precipitation_mm:.5,unit:'mm'}))}
 render(<HomeEmergencyDashboard {...p}/>);await screen.findByText('No currently verified open shelters are available in this directory.')
 expect(screen.getByRole('heading',{name:'Next 24 full forecast hours: 12 mm'})).toBeTruthy()
 expect(screen.getByText(/Humidity: 70%\. Wind: 12 km\/h/)).toBeTruthy()
 expect(screen.getAllByText(/Slight rain/)).toHaveLength(2)
 expect(screen.getByText('Validated flood forecast unavailable for this location.')).toBeTruthy()
 expect(fetch).toHaveBeenCalledTimes(1)
})
it('missing temperature preserves other valid current weather rather than hiding it',async()=>{
 const p=props();p.session.data.current.temperature_c=null;p.session.data.current.humidity_percent=70
 render(<HomeEmergencyDashboard {...p}/>);await screen.findByText('No currently verified open shelters are available in this directory.')
 expect(screen.getByRole('heading',{name:'Temperature unavailable.'})).toBeTruthy();expect(screen.getByText(/Humidity: 70%/)).toBeTruthy()
})
