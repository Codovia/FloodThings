import { act, cleanup, renderHook } from '@testing-library/react'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import useHomeGeolocation, { GPS_TIMEOUT_MS } from './useHomeGeolocation.js'
let get, success, failure, revision, selected, watcher
beforeEach(() => {
  sessionStorage.clear(); vi.useFakeTimers(); vi.stubGlobal('isSecureContext', true)
  vi.stubGlobal('fetch',vi.fn(async url=>({ok:true,json:async()=>url==='/api/location/provider'?{provider:'MapTiler'}:{status:'disabled'}})))
  revision = { current: 0 }; selected = vi.fn(); watcher = vi.fn()
  get = vi.fn((yes, no) => { success = yes; failure = no })
  Object.defineProperty(navigator, 'geolocation', { configurable: true, value: { getCurrentPosition: get, watchPosition: watcher } })
})
afterEach(() => { cleanup(); vi.useRealTimers(); vi.unstubAllGlobals(); delete navigator.geolocation })
const position = (latitude=13.34, longitude=74.74, accuracy=50) => ({ coords: { latitude, longitude, accuracy }, timestamp: Date.now() })
const mount = () => renderHook(({ active=true, hasSelection=false }={}) => useHomeGeolocation(active, revision, hasSelection, selected), { initialProps: { active:true } })
it('automatically makes one bounded request and retains the actual point and accuracy', () => {
  const h = mount(); expect(get).toHaveBeenCalledTimes(1)
  expect(get.mock.calls[0][2]).toEqual({ enableHighAccuracy:true, timeout:10000, maximumAge:0 })
  act(() => success(position()))
  expect(selected).toHaveBeenCalledWith(expect.objectContaining({ latitude:13.34, longitude:74.74, accuracy_m:50, kind:'gps' }))
  expect(h.result.current.status).toBe('inside'); expect(watcher).not.toHaveBeenCalled()
  h.rerender({ active:false }); h.rerender({ active:true }); expect(get).toHaveBeenCalledTimes(1)
})
it.each([[1,'denied'],[2,'unavailable'],[3,'timeout']])('preserves fallback on browser error %s', (code, state) => {
  const h = mount(); act(() => failure({ code })); expect(h.result.current.status).toBe(state); expect(selected).not.toHaveBeenCalled()
})
it('times out even when the browser never calls back and discards a late result', () => {
  const h = mount(); act(() => vi.advanceTimersByTime(GPS_TIMEOUT_MS)); expect(h.result.current.status).toBe('timeout')
  act(() => success(position())); expect(selected).not.toHaveBeenCalled()
})
it('does not override manual choice or district filtering while GPS is pending', () => {
  const h = mount(); revision.current++; act(() => h.result.current.cancel()); act(() => success(position()))
  expect(selected).not.toHaveBeenCalled(); expect(h.result.current.status).toBe('manual')
})
it('does not replace a point chosen on another route on first Home visit', () => {
  const h = mount(); h.unmount(); get.mockClear(); sessionStorage.clear()
  renderHook(() => useHomeGeolocation(true, revision, true, selected)); expect(get).not.toHaveBeenCalled()
})
it('refuses an insecure context without invoking the browser', () => {
  vi.stubGlobal('isSecureContext', false); const h = mount(); expect(h.result.current.status).toBe('insecure'); expect(get).not.toHaveBeenCalled()
})
it('handles unsupported APIs and policy exceptions', () => {
  delete navigator.geolocation; const h = mount(); expect(h.result.current.status).toBe('unsupported')
  Object.defineProperty(navigator, 'geolocation', { configurable:true, value:{ getCurrentPosition: () => { throw Error('Policy') } } })
  act(() => h.result.current.request()); expect(h.result.current.status).toBe('unavailable')
})
it('reports outside Karnataka and keeps exact GPS coordinates for weather', () => {
  const h = mount(); act(() => success(position(28.61,77.21))); expect(h.result.current.status).toBe('outside'); expect(selected.mock.calls[0][0].latitude).toBe(28.61)
})
it.each([position(100), position(13,74,NaN), { ...position(), timestamp:0 }])('rejects invalid or stale browser positions', p => {
  const h = mount(); act(() => success(p)); expect(h.result.current.status).toBe('invalid'); expect(selected).not.toHaveBeenCalled()
})
it('discards callbacks after leaving Home and only retries on an explicit action', () => {
  const h = mount(); h.rerender({ active:false }); expect(h.result.current.status).toBe('cancelled'); act(() => success(position())); expect(selected).not.toHaveBeenCalled()
  h.rerender({ active:true }); expect(get).toHaveBeenCalledTimes(1); act(() => h.result.current.request()); expect(get).toHaveBeenCalledTimes(2)
})

it('a fresh application retries automatic location without storing coordinates', () => {
 const h=mount();act(()=>success(position()));h.unmount();get.mockClear();mount();expect(get).toHaveBeenCalledTimes(1);expect(Object.entries(sessionStorage)).toEqual([['floodpulse-home-location-attempted','1']])
})

it('coarse GPS keeps statewide fallback without weather selection or reverse-geocoder calls',()=>{
 const h=mount();act(()=>success(position(13.34,74.74,279949)))
 expect(h.result.current.status).toBe('coarse');expect(h.result.current.gps).toBeNull();expect(h.result.current.message).toContain('Approximate location — select your town');expect(selected).not.toHaveBeenCalled();expect(fetch).toHaveBeenCalledTimes(1);expect(fetch.mock.calls[0][0]).not.toContain('latitude')
})
it('accepts a verified provider label without changing actual coordinates or assigning a district ID',async()=>{
 fetch.mockImplementation(async url=>({ok:true,json:async()=>url==='/api/location/provider'?{provider:'MapTiler'}:({status:'available',name:'Verified fixture town, Fixture context',accuracy_supported:true,geometry_verification:'provider_locality_polygon_covers_accuracy',feature_id:'municipality.test-only',source:{provider:'MapTiler'},administrative_identity_status:'provider_context_not_canonical_directory_join'})}))
 const h=mount();await act(async()=>success(position()))
 expect(h.result.current.gps.name).toBe('Verified fixture town, Fixture context')
 expect(selected).toHaveBeenLastCalledWith(expect.objectContaining({latitude:13.34,longitude:74.74,accuracy_m:50}))
 expect(selected.mock.calls.at(-1)[0].district_id).toBeUndefined()
 expect(fetch).toHaveBeenCalledWith('/api/location/reverse',expect.objectContaining({method:'POST',body:JSON.stringify({latitude:13.34,longitude:74.74,accuracy_m:50})}))
})
it('manual choice aborts pending geocoding and rejects even an ignored-abort late name',async()=>{
 let resolve;fetch.mockImplementation(()=>new Promise(r=>{resolve=r}))
 const h=mount();act(()=>success(position()));expect(selected).toHaveBeenCalledTimes(1)
 revision.current++;act(()=>h.result.current.cancel());expect(fetch.mock.calls[0][1].signal.aborted).toBe(true)
 await act(async()=>resolve({ok:true,json:async()=>({status:'available',name:'Late fixture',accuracy_supported:true,geometry_verification:'provider_locality_polygon_covers_accuracy',source:{provider:'MapTiler'}})}))
 expect(selected).toHaveBeenCalledTimes(1);expect(h.result.current.status).toBe('manual');expect(h.result.current.gps).toBeNull()
})
it('disabled naming leaves accepted precise GPS and makes manual naming available',async()=>{
 const h=mount();await act(async()=>success(position()));expect(selected).toHaveBeenCalledTimes(1);expect(h.result.current.gps.name).toBe('GPS-selected point');expect(h.result.current.message).toContain('Place naming is unavailable')
})
it('times out naming without discarding the accepted weather coordinates',async()=>{
 fetch.mockImplementation((_,{signal})=>new Promise((resolve,reject)=>signal.addEventListener('abort',()=>reject(new DOMException('Aborted','AbortError')))))
 const h=mount();act(()=>success(position()));await act(async()=>vi.advanceTimersByTimeAsync(GPS_TIMEOUT_MS))
 expect(h.result.current.gps.latitude).toBe(13.34);expect(selected).toHaveBeenCalledTimes(1);expect(h.result.current.message).toContain('Place naming timed out')
})

it.each([150,1200,8000])('accepts ±%s m for approximate weather without treating it as river precision', async accuracy=>{
 const h=mount();await act(async()=>success(position(13.34,74.74,accuracy)))
 expect(selected.mock.calls[0][0].accuracy_m).toBe(accuracy);expect(h.result.current.gps.latitude).toBe(13.34)
})
it('automatically names a live browser fix through the permitted client provider',async()=>{
 fetch.mockImplementation(async url=>({ok:true,json:async()=>url==='/api/location/provider'?{provider:'BigDataCloud'}:{city:'TEST ONLY city',countryCode:'IN',lookupSource:'coordinates',latitude:13.34,longitude:74.74}}))
 const h=mount();await act(async()=>success(position(13.34,74.74,1200)))
 expect(h.result.current.gps.name).toBe('TEST ONLY city');expect(h.result.current.message).toContain('Approximate provider town label')
 expect(fetch.mock.calls[1][0]).toContain('latitude=13.34');expect(fetch.mock.calls.some(([u])=>u==='/api/location/reverse')).toBe(false)
})
it('a coarse browser fix uses a separately attributed network point without sending coarse coordinates',async()=>{
 fetch.mockResolvedValue({ok:true,json:async()=>({city:'TEST ONLY network city',countryCode:'IN',lookupSource:'ipGeolocation',latitude:13.3,longitude:74.7})})
 const h=mount();await act(async()=>success(position(13.34,74.74,279949)))
 expect(selected).toHaveBeenCalledWith(expect.objectContaining({kind:'network',accuracy_m:null,latitude:13.3}));expect(h.result.current.message).toContain('uncertainty unknown')
 expect(fetch.mock.calls[0][0]).not.toContain('latitude');expect(h.result.current.gps).toBeNull()
})
it('ignores a late coarse fix after manual selection',()=>{
 const h=mount();revision.current++;act(()=>h.result.current.cancel());act(()=>success(position(13.34,74.74,279949)))
 expect(fetch).not.toHaveBeenCalled();expect(selected).not.toHaveBeenCalled()
})
