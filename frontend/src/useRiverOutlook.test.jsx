import {act,cleanup,renderHook} from '@testing-library/react'
import {afterEach,beforeEach,expect,it,vi} from 'vitest'
import useRiverOutlook,{usableRiver} from './useRiverOutlook.js'
const point={latitude:13.4,longitude:74.7,accuracy_m:40},NOW=Date.parse('2026-10-13T11:00:00Z')
const body=(p=point)=>({status:'partial',source:{data_kind:'external_modelled_river_forecast'},requested_model:'forecast_v4',reach:{name:'TEST ONLY river',verified_grid:true,expected_grid:{latitude:13.4,longitude:74.7}},grid_location:{latitude:13.4,longitude:74.7},units:'m³/s',timezone:'GMT',retrieved_at:new Date(NOW).toISOString(),fresh_until:new Date(NOW+3600000).toISOString(),viewing_point:p,forecast:Array.from({length:7},(_,i)=>({date:`2026-10-${13+i}`,river_discharge:i===0?null:3}))})
const reply=data=>({ok:true,json:async()=>data}),flush=()=>act(async()=>{await Promise.resolve();await Promise.resolve()})
beforeEach(()=>{vi.useFakeTimers();vi.setSystemTime(NOW);vi.stubGlobal('fetch',vi.fn(async()=>reply({status:'unsupported',message:'No approved reach'})))})
afterEach(()=>{cleanup();vi.unstubAllGlobals();vi.useRealTimers()})
it('no selection makes no source call; one actual point uses POST and rerenders do not repeat',async()=>{
 const h=renderHook(({p})=>useRiverOutlook(p),{initialProps:{p:null}});expect(fetch).not.toHaveBeenCalled()
 h.rerender({p:point});await flush();expect(h.result.current.data.status).toBe('unsupported');expect(fetch).toHaveBeenCalledTimes(1)
 expect(fetch.mock.calls[0][1]).toMatchObject({method:'POST',body:JSON.stringify(point)})
 h.rerender({p:{...point,name:'Renamed without moving'}});await flush();expect(fetch).toHaveBeenCalledTimes(1)
})
it('changing points aborts stale responses before they can overwrite the selected point',async()=>{
 let resolve;fetch.mockImplementationOnce(()=>new Promise(r=>{resolve=r}))
 const h=renderHook(({p})=>useRiverOutlook(p),{initialProps:{p:point}}),signal=fetch.mock.calls[0][1].signal
 h.rerender({p:{...point,latitude:14}});await flush();expect(signal.aborted).toBe(true)
 await act(async()=>resolve(reply(body())));expect(h.result.current.data.status).toBe('unsupported')
})
it('manual refresh is explicit; failed refresh clears retained data',async()=>{
 fetch.mockResolvedValueOnce(reply(body()))
 const h=renderHook(()=>useRiverOutlook(point));await flush();expect(usableRiver(h.result.current.data,point,NOW)).toBe(true)
 fetch.mockRejectedValue(new TypeError('Controlled network failure'));act(()=>h.result.current.refresh());await flush();expect(h.result.current.data).toBeNull();expect(h.result.current.error).toContain('could not be checked')
})
it.each(['unverified_grid','incorrect_point','stale','units','model','timezone','duplicate','negative'])('rejects %s instead of inventing a flood outlook',async issue=>{
 const data=body()
 if(issue==='unverified_grid')data.reach.verified_grid=false
 if(issue==='incorrect_point')data.viewing_point={...point,latitude:14}
 if(issue==='stale')data.retrieved_at=new Date(NOW-3600000).toISOString()
 if(issue==='units')data.units='mm'
 if(issue==='model')data.requested_model='historical_v5'
 if(issue==='timezone')data.timezone='Asia/Kolkata'
 if(issue==='duplicate')data.forecast[1].date=data.forecast[0].date
 if(issue==='negative')data.forecast[1].river_discharge=-1
 fetch.mockResolvedValue(reply(data));const h=renderHook(()=>useRiverOutlook(point));await flush();expect(h.result.current.data).toBeNull();expect(h.result.current.error).toContain('could not be checked')
})
it('freshness expiry hides a retained river response without an automatic source request',async()=>{
 fetch.mockResolvedValue(reply(body()));const h=renderHook(()=>useRiverOutlook(point));await flush()
 await act(async()=>vi.advanceTimersByTimeAsync(3600000));expect(usableRiver(h.result.current.data,point,h.result.current.now)).toBe(false);expect(fetch).toHaveBeenCalledTimes(1)
})
