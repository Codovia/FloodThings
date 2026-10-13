import React from 'react'
import {cleanup,fireEvent,render,screen,waitFor} from '@testing-library/react'
import {afterEach,beforeEach,expect,it,vi} from 'vitest'
import HomeEmergencyDashboard from './HomeEmergencyDashboard.jsx'
const mapProps=vi.hoisted(()=>({current:null}))
vi.mock('./HomeFloodMap.jsx',()=>({default:props=>{mapProps.current=props;return <div>Home map fixture</div>}}))
vi.mock('./LocationDirectorySelector.jsx',()=>({default:({onChoose,onDistrict})=><><button onClick={()=>onChoose({name:'Verified fixture locality',latitude:13.4,longitude:74.7,locality_id:'test-only'})}>Choose fixture locality</button><button onClick={()=>onDistrict({id:'test-district',name:'Fixture district'})}>Choose district only</button></>}))
const point={name:'GPS-selected point',latitude:13.4,longitude:74.7,accuracy_m:40,kind:'gps'}
const props=()=>({point,session:{data:{retrieved_at:new Date().toISOString(),current:{valid_at:new Date().toISOString(),temperature_c:27,precipitation_mm:1,interval_seconds:900},forecast:[]},freshness:'fresh',loading:false,error:null,refresh:vi.fn()},location:{message:'GPS test receipt',status:'inside',request:vi.fn()},choosePoint:vi.fn(),chooseDistrict:vi.fn(),navigate:vi.fn()})
const unsupported={status:'unsupported',message:'No verified association.'}
beforeEach(()=>vi.stubGlobal('fetch',vi.fn(async()=>({ok:true,json:async()=>unsupported}))))
afterEach(()=>{cleanup();vi.unstubAllGlobals();vi.useRealTimers()})
it('shows weather and exact unavailable flood wording while removing Home historical/shelter calls and content',async()=>{
 render(<HomeEmergencyDashboard {...props()}/>);await screen.findByText('No verified river-grid association is available for this point.')
 expect(screen.getByRole('heading',{name:'27 °C'})).toBeTruthy();expect(screen.getByText('Validated flood forecast unavailable for this location.')).toBeTruthy();expect(screen.getByText('Next-24-hour total unavailable')).toBeTruthy()
 expect(screen.queryByText(/Historical flood evidence|Verified Open shelters|56 reviewed/)).toBeNull();expect(screen.queryByRole('button',{name:'Refresh shelters'})).toBeNull()
 expect(fetch).toHaveBeenCalledTimes(1);expect(fetch.mock.calls[0][0]).toBe('/api/river-outlook');expect(mapProps.current.river).toBeNull();expect(mapProps.current.features).toBeUndefined();expect(mapProps.current.shelters).toBeUndefined()
})
it('district-only fallback cannot display cached default weather or invent a point',async()=>{
 const p=props();render(<HomeEmergencyDashboard {...p} point={null} districtId="fixture" district={{name:'Fixture district'}}/>);
 expect(screen.queryByRole('heading',{name:'27 °C'})).toBeNull();expect(mapProps.current.point).toBeNull();expect(fetch).not.toHaveBeenCalled()
 fireEvent.click(screen.getByText('Choose district only'));expect(p.chooseDistrict).toHaveBeenCalledWith({id:'test-district',name:'Fixture district'})
 fireEvent.click(screen.getByText('Choose fixture locality'));expect(p.choosePoint).toHaveBeenCalledWith(expect.objectContaining({locality_id:'test-only'}))
})
it.each(['loading','failure','stale'])('shows explicit %s weather without a current estimate',async kind=>{
 const p=props();p.session={...p.session,loading:kind==='loading',error:kind==='failure'?'Controlled provider failure':null,freshness:kind==='loading'?'refreshing':kind==='failure'?'unavailable':'stale'}
 render(<HomeEmergencyDashboard {...p}/>);await screen.findByText('No verified river-grid association is available for this point.')
 expect(screen.queryByRole('heading',{name:'27 °C'})).toBeNull();expect(screen.getByRole('heading',{name:kind==='loading'?'Loading weather…':'Current weather unavailable.'})).toBeTruthy()
 if(kind==='failure')expect(screen.getByRole('alert').textContent).toContain('Controlled provider failure')
})
it('coarse fallback is prominent and requests neither weather nor river for an unaccepted point',()=>{
 render(<HomeEmergencyDashboard {...props()} point={null} location={{message:'Accuracy too large',status:'coarse'}}/>);
 expect(screen.getByRole('heading',{name:'Approximate location — select your town'})).toBeTruthy();expect(screen.getByText('Nearby flood possibility cannot currently be assessed reliably. Check official local warnings.')).toBeTruthy();expect(screen.getByText('Not connected')).toBeTruthy();expect(fetch).not.toHaveBeenCalled()
})
it('shows WMO current conditions, optional fields and a complete hourly total without flood inference',async()=>{
 const p=props(),begin=Math.ceil((Date.now()+19800000)/3600000)*3600000-19800000
 p.session.data.current={...p.session.data.current,weather_code:61,humidity_percent:70,wind_speed:12,wind_speed_unit:'km/h'}
 p.session.data.hourly_precipitation={status:'available',timezone:'Asia/Kolkata',unit:'mm',interval_seconds:3600,interval_semantics:'preceding_hour',source:{name:'Open-Meteo'},intervals:Array.from({length:24},(_,i)=>({start:new Date(begin+i*3600000).toISOString(),end:new Date(begin+(i+1)*3600000).toISOString(),precipitation_mm:.5,unit:'mm'}))}
 render(<HomeEmergencyDashboard {...p}/>);await screen.findByText('No verified river-grid association is available for this point.')
 expect(screen.getByRole('heading',{name:'Next 24 full forecast hours: 12 mm'})).toBeTruthy();expect(screen.getByText(/Humidity: 70%\. Wind: 12 km\/h/)).toBeTruthy();expect(screen.getAllByText(/Slight rain/)).toHaveLength(1)
 expect(screen.getByText('Validated flood forecast unavailable for this location.')).toBeTruthy();expect(fetch).toHaveBeenCalledTimes(1)
})
it('missing temperature preserves other valid current fields',async()=>{
 const p=props();p.session.data.current.temperature_c=null;p.session.data.current.humidity_percent=70
 render(<HomeEmergencyDashboard {...p}/>);await screen.findByText('No verified river-grid association is available for this point.')
 expect(screen.getByRole('heading',{name:'Temperature unavailable.'})).toBeTruthy();expect(screen.getByText(/Humidity: 70%/)).toBeTruthy()
})
