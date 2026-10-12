import { act, cleanup, renderHook } from '@testing-library/react'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import useHomeGeolocation, { GPS_TIMEOUT_MS } from './useHomeGeolocation.js'
let get, success, failure, revision, selected, watcher
beforeEach(() => {
  sessionStorage.clear(); vi.useFakeTimers(); vi.stubGlobal('isSecureContext', true)
  revision = { current: 0 }; selected = vi.fn(); watcher = vi.fn()
  get = vi.fn((yes, no) => { success = yes; failure = no })
  Object.defineProperty(navigator, 'geolocation', { configurable: true, value: { getCurrentPosition: get, watchPosition: watcher } })
})
afterEach(() => { cleanup(); vi.useRealTimers(); vi.unstubAllGlobals(); delete navigator.geolocation })
const position = (latitude=13.34, longitude=74.74, accuracy=50) => ({ coords: { latitude, longitude, accuracy }, timestamp: Date.now() })
const mount = () => renderHook(({ active=true, hasSelection=false }={}) => useHomeGeolocation(active, revision, hasSelection, selected), { initialProps: { active:true } })
it('automatically makes one bounded request and retains the actual point and accuracy', () => {
  const h = mount(); expect(get).toHaveBeenCalledTimes(1)
  expect(get.mock.calls[0][2]).toEqual({ enableHighAccuracy:false, timeout:10000, maximumAge:0 })
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

it('tab-session flag prevents another automatic request on application reload without storing coordinates', () => {
 const h=mount();act(()=>success(position()));h.unmount();get.mockClear();mount();expect(get).not.toHaveBeenCalled();expect(Object.entries(sessionStorage)).toEqual([['floodpulse-home-location-attempted','1']])
})
