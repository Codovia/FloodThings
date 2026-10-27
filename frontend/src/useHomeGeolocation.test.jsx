import { act, cleanup, renderHook } from '@testing-library/react'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import useHomeGeolocation, { GPS_TIMEOUT_MS, REFINE_MS } from './useHomeGeolocation.js'
// `get` is the browser's watchPosition: Home refines the fix for a bounded time (preciseLocation.js).
let get, clear, success, failure, revision, selected
beforeEach(() => {
  sessionStorage.clear(); vi.useFakeTimers(); vi.stubGlobal('isSecureContext', true)
  vi.stubGlobal('fetch',vi.fn(async url=>({ok:true,json:async()=>url==='/api/location/provider'?{provider:'MapTiler'}:{status:'disabled'}})))
  revision = { current: 0 }; selected = vi.fn(); clear = vi.fn()
  get = vi.fn((yes, no) => { success = yes; failure = no; return 1 })
  Object.defineProperty(navigator, 'geolocation', { configurable: true, value: { watchPosition: get, clearWatch: clear } })
})
afterEach(() => { cleanup(); vi.useRealTimers(); vi.unstubAllGlobals(); delete navigator.geolocation })
// ±15 m is good enough to stop refining at once; coarser fixes wait for the improvement window.
const position = (latitude=13.34, longitude=74.74, accuracy=15) => ({ coords: { latitude, longitude, accuracy }, timestamp: Date.now() })
const fix = async p => act(async () => success(p))
const settle = async p => act(async () => { success(p); await vi.advanceTimersByTimeAsync(REFINE_MS) })
const mount = () => renderHook(({ active=true, hasSelection=false }={}) => useHomeGeolocation(active, revision, hasSelection, selected), { initialProps: { active:true } })
it('automatically makes one bounded request and retains the actual point and accuracy', async () => {
  const h = mount(); expect(get).toHaveBeenCalledTimes(1)
  expect(get.mock.calls[0][2]).toEqual({ enableHighAccuracy:true, timeout:10000, maximumAge:0 })
  await fix(position())
  expect(selected).toHaveBeenCalledWith(expect.objectContaining({ latitude:13.34, longitude:74.74, accuracy_m:15, kind:'gps' }))
  expect(h.result.current.status).toBe('inside'); expect(clear).toHaveBeenCalledWith(1)
  h.rerender({ active:false }); h.rerender({ active:true }); expect(get).toHaveBeenCalledTimes(1)
})
it('refines a coarse first fix, shows progress, and uses the most accurate one', async () => {
  const h = mount()
  await fix(position(13.3, 74.7, 850))
  expect(h.result.current.status).toBe('requesting'); expect(h.result.current.progress).toBe(850)
  expect(h.result.current.message).toContain('±850 m so far'); expect(selected).not.toHaveBeenCalled()
  await fix(position(13.341, 74.741, 60)); expect(h.result.current.progress).toBe(60)
  await fix(position(13.2, 74.6, 400)); expect(h.result.current.progress).toBe(60) // a worse later fix is not used
  await act(async () => vi.advanceTimersByTimeAsync(REFINE_MS))
  expect(selected).toHaveBeenCalledTimes(1); expect(selected.mock.calls[0][0]).toMatchObject({ latitude:13.341, longitude:74.741, accuracy_m:60 })
  expect(clear).toHaveBeenCalledWith(1)
})
it('the first fix replaces the ten-second no-answer timeout with the improvement window', async () => {
  const h = mount()
  await act(async () => vi.advanceTimersByTimeAsync(GPS_TIMEOUT_MS - 1000))
  await fix(position(13.3, 74.7, 300))
  await act(async () => vi.advanceTimersByTimeAsync(2000)) // past the original timeout: still refining, no fallback
  expect(h.result.current.status).toBe('requesting'); expect(fetch).not.toHaveBeenCalled()
  await act(async () => vi.advanceTimersByTimeAsync(REFINE_MS))
  expect(selected.mock.calls[0][0].accuracy_m).toBe(300)
})
it.each([[1,'denied'],[2,'unavailable'],[3,'timeout']])('preserves fallback on browser error %s', async (code, state) => {
  const h = mount(); await act(async () => failure({ code })); expect(h.result.current.status).toBe(state); expect(selected).not.toHaveBeenCalled()
})
it('times out even when the browser never calls back and discards a late result', async () => {
  const h = mount(); await act(async () => vi.advanceTimersByTimeAsync(GPS_TIMEOUT_MS)); expect(h.result.current.status).toBe('timeout')
  await fix(position()); expect(selected).not.toHaveBeenCalled()
})
it('does not override manual choice or district filtering while GPS is pending', async () => {
  const h = mount(); revision.current++; act(() => h.result.current.cancel()); expect(clear).toHaveBeenCalledWith(1)
  await fix(position()); expect(selected).not.toHaveBeenCalled(); expect(h.result.current.status).toBe('manual')
})
it('does not replace a point chosen on another route on first Home visit', () => {
  const h = mount(); h.unmount(); get.mockClear(); sessionStorage.clear()
  renderHook(() => useHomeGeolocation(true, revision, true, selected)); expect(get).not.toHaveBeenCalled()
})
it('refuses an insecure context without invoking the browser', () => {
  vi.stubGlobal('isSecureContext', false); const h = mount(); expect(h.result.current.status).toBe('insecure'); expect(get).not.toHaveBeenCalled()
})
it('handles unsupported APIs and policy exceptions', async () => {
  delete navigator.geolocation; const h = mount(); expect(h.result.current.status).toBe('unsupported')
  Object.defineProperty(navigator, 'geolocation', { configurable:true, value:{ getCurrentPosition: () => { throw Error('Policy') } } })
  await act(async () => h.result.current.request()); expect(h.result.current.status).toBe('unavailable')
})
it('reports outside Karnataka and keeps exact GPS coordinates for weather', async () => {
  const h = mount(); await fix(position(28.61,77.21)); expect(h.result.current.status).toBe('outside'); expect(selected.mock.calls[0][0].latitude).toBe(28.61)
})
it('rejects a stale browser position', async () => {
  const h = mount(); await fix({ ...position(), timestamp:0 }); expect(h.result.current.status).toBe('invalid'); expect(selected).not.toHaveBeenCalled()
})
it.each([position(100), position(13,74,NaN)])('never uses impossible coordinates or a fix without accuracy', async p => {
  const h = mount(); await fix(p); expect(selected).not.toHaveBeenCalled()
  await act(async () => vi.advanceTimersByTimeAsync(GPS_TIMEOUT_MS)); expect(h.result.current.status).toBe('timeout'); expect(selected.mock.calls.some(([v]) => v.kind === 'gps')).toBe(false)
})
it('discards callbacks after leaving Home and only retries on an explicit action', async () => {
  const h = mount(); h.rerender({ active:false }); expect(h.result.current.status).toBe('cancelled'); expect(clear).toHaveBeenCalledWith(1)
  await fix(position()); expect(selected).not.toHaveBeenCalled()
  h.rerender({ active:true }); expect(get).toHaveBeenCalledTimes(1); act(() => h.result.current.request()); expect(get).toHaveBeenCalledTimes(2)
})

it('a fresh application retries automatic location without storing coordinates', async () => {
 const h=mount();await fix(position());h.unmount();get.mockClear();mount();expect(get).toHaveBeenCalledTimes(1);expect(Object.entries(sessionStorage)).toEqual([['floodpulse-home-location-attempted','1']])
})

it('coarse GPS keeps statewide fallback without weather selection or reverse-geocoder calls',async()=>{
 const h=mount();await settle(position(13.34,74.74,279949))
 expect(h.result.current.status).toBe('coarse');expect(h.result.current.gps).toBeNull();expect(h.result.current.message).toContain('Approximate location — select your town');expect(selected).not.toHaveBeenCalled();expect(fetch).toHaveBeenCalledTimes(1);expect(fetch.mock.calls[0][0]).not.toContain('latitude')
})
it('accepts a verified provider label without changing actual coordinates or assigning a district ID',async()=>{
 fetch.mockImplementation(async url=>({ok:true,json:async()=>url==='/api/location/provider'?{provider:'MapTiler'}:({status:'available',name:'Verified fixture town, Fixture context',accuracy_supported:true,geometry_verification:'provider_locality_polygon_covers_accuracy',feature_id:'municipality.test-only',source:{provider:'MapTiler'},administrative_identity_status:'provider_context_not_canonical_directory_join'})}))
 const h=mount();await fix(position())
 expect(h.result.current.gps.name).toBe('Verified fixture town, Fixture context')
 expect(selected).toHaveBeenLastCalledWith(expect.objectContaining({latitude:13.34,longitude:74.74,accuracy_m:15}))
 expect(selected.mock.calls.at(-1)[0].district_id).toBeUndefined()
 expect(fetch).toHaveBeenCalledWith('/api/location/reverse',expect.objectContaining({method:'POST',body:JSON.stringify({latitude:13.34,longitude:74.74,accuracy_m:15})}))
})
it('manual choice aborts pending geocoding and rejects even an ignored-abort late name',async()=>{
 let resolve;fetch.mockImplementation(()=>new Promise(r=>{resolve=r}))
 const h=mount();await fix(position());expect(selected).toHaveBeenCalledTimes(1)
 revision.current++;act(()=>h.result.current.cancel());expect(fetch.mock.calls[0][1].signal.aborted).toBe(true)
 await act(async()=>resolve({ok:true,json:async()=>({status:'available',name:'Late fixture',accuracy_supported:true,geometry_verification:'provider_locality_polygon_covers_accuracy',source:{provider:'MapTiler'}})}))
 expect(selected).toHaveBeenCalledTimes(1);expect(h.result.current.status).toBe('manual');expect(h.result.current.gps).toBeNull()
})
it('disabled naming leaves accepted precise GPS and makes manual naming available',async()=>{
 const h=mount();await fix(position());expect(selected).toHaveBeenCalledTimes(1);expect(h.result.current.gps.name).toBe('GPS-selected point');expect(h.result.current.message).toContain('The place name is unavailable')
})
it('times out naming without discarding the accepted weather coordinates',async()=>{
 fetch.mockImplementation((_,{signal})=>new Promise((resolve,reject)=>signal.addEventListener('abort',()=>reject(new DOMException('Aborted','AbortError')))))
 const h=mount();await fix(position());await act(async()=>vi.advanceTimersByTimeAsync(GPS_TIMEOUT_MS))
 expect(h.result.current.gps.latitude).toBe(13.34);expect(selected).toHaveBeenCalledTimes(1);expect(h.result.current.message).toContain('Place naming timed out')
})

it.each([150,1200,8000])('accepts ±%s m for approximate weather without treating it as river precision', async accuracy=>{
 const h=mount();await settle(position(13.34,74.74,accuracy))
 expect(selected.mock.calls[0][0].accuracy_m).toBe(accuracy);expect(h.result.current.gps.latitude).toBe(13.34)
})
it('automatically names a live browser fix through the permitted client provider',async()=>{
 fetch.mockImplementation(async url=>({ok:true,json:async()=>url==='/api/location/provider'?{provider:'BigDataCloud'}:{city:'TEST ONLY city',countryCode:'IN',lookupSource:'coordinates',latitude:13.34,longitude:74.74}}))
 const h=mount();await settle(position(13.34,74.74,1200))
 expect(h.result.current.gps.name).toBe('TEST ONLY city');expect(h.result.current.message).toContain('Town name is approximate (BigDataCloud)')
 expect(fetch.mock.calls[1][0]).toContain('latitude=13.34');expect(fetch.mock.calls.some(([u])=>u==='/api/location/reverse')).toBe(false)
})
it('a coarse browser fix uses a separately attributed network point without sending coarse coordinates',async()=>{
 fetch.mockResolvedValue({ok:true,json:async()=>({city:'TEST ONLY network city',countryCode:'IN',lookupSource:'ipGeolocation',latitude:13.3,longitude:74.7})})
 const h=mount();await settle(position(13.34,74.74,279949))
 expect(selected).toHaveBeenCalledWith(expect.objectContaining({kind:'network',accuracy_m:null,latitude:13.3}));expect(h.result.current.message).toContain('uncertainty unknown')
 expect(fetch.mock.calls[0][0]).not.toContain('latitude');expect(h.result.current.gps).toBeNull()
})
it('ignores a late coarse fix after manual selection',async()=>{
 const h=mount();revision.current++;act(()=>h.result.current.cancel());await settle(position(13.34,74.74,279949))
 expect(fetch).not.toHaveBeenCalled();expect(selected).not.toHaveBeenCalled()
})

it('overlapping browser timeout/error starts only one approximate network lookup',async()=>{
 fetch.mockImplementation(()=>new Promise(()=>{}))
 const h=mount();await act(async()=>vi.advanceTimersByTimeAsync(GPS_TIMEOUT_MS));expect(fetch).toHaveBeenCalledTimes(1)
 await act(async()=>failure({code:3}));expect(fetch).toHaveBeenCalledTimes(1);expect(h.result.current.status).toBe('timeout')
})
