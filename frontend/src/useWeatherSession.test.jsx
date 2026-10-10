import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { act, cleanup, renderHook } from '@testing-library/react'
import useWeatherSession, { FRESHNESS_MS, RETRY_DELAYS_MS, freshnessOf, retrievalTime } from './useWeatherSession.js'
import { DEFAULT_POINT } from './WeatherLocationSelector.jsx'

const BASE = new Date('2026-10-08T06:00:00Z')
const UDUPI = { latitude: 13.34, longitude: 74.74 }
const fixture = (point = DEFAULT_POINT, retrieved = new Date().toISOString(), temperature = 27) => ({
  status: 'available', location: point, retrieved_at: retrieved,
  current: { temperature_c: temperature, valid_at: '2026-10-08T11:30:00+05:30' },
  forecast: Array.from({ length: 7 }, (_, i) => ({ date: `2026-10-${8 + i}`, temperature_min_c: 20, temperature_max_c: 30, precipitation_mm: 1 })),
  grid_location: { latitude: 13.35, longitude: 74.75 }, forecast_issued_at: null,
})
// pad fixture dates, never production dates.
const body = (...args) => { const result = fixture(...args); result.forecast.forEach(d => { d.date = d.date.replace(/-(\d)$/, '-0$1') }); return result }
const reply = json => ({ ok: true, json: async () => json })
const flush = () => act(async () => { await Promise.resolve(); await Promise.resolve() })
const advance = ms => act(async () => { await vi.advanceTimersByTimeAsync(ms) })
const event = (name, target = window) => act(() => target.dispatchEvent(new Event(name)))
const hidden = value => { vi.spyOn(document, 'hidden', 'get').mockReturnValue(value); event('visibilitychange', document) }

beforeEach(() => {
  vi.useFakeTimers(); vi.setSystemTime(BASE)
  vi.spyOn(document, 'hidden', 'get').mockReturnValue(false)
  vi.spyOn(navigator, 'onLine', 'get').mockReturnValue(true)
  vi.stubGlobal('fetch', vi.fn(async url => {
    const params = new URL(url, 'http://local').searchParams
    return reply(body(params.has('latitude') ? { latitude: +params.get('latitude'), longitude: +params.get('longitude') } : DEFAULT_POINT))
  }))
})
afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals(); vi.useRealTimers() })

it('loads default immediately with fresh backend clock, preserving seven dates/grid and issue-time null', async () => {
  const { result } = renderHook(() => useWeatherSession(null))
  expect(result.current.freshness).toBe('refreshing'); expect(fetch).toHaveBeenCalledTimes(1)
  await flush()
  expect(result.current.freshness).toBe('fresh')
  expect(result.current.data.retrieved_at).toBe(BASE.toISOString())
  expect(result.current.data.forecast).toHaveLength(7)
  expect(result.current.data.forecast.map(d => d.date)).toEqual(['2026-10-08','2026-10-09','2026-10-10','2026-10-11','2026-10-12','2026-10-13','2026-10-14'])
  expect(result.current.data.grid_location).toEqual({ latitude: 13.35, longitude: 74.75 })
  expect(result.current.data.forecast_issued_at).toBeNull()
})
it('uses backend retrieval age, not mount time, and automatically refreshes at six hours exactly', async () => {
  fetch.mockResolvedValueOnce(reply(body(DEFAULT_POINT, new Date(BASE.getTime() - 60 * 60 * 1000).toISOString())))
  const { result } = renderHook(() => useWeatherSession(null)); await flush()
  await advance(5 * 60 * 60 * 1000 - 1)
  expect(fetch).toHaveBeenCalledTimes(1); expect(result.current.freshness).toBe('fresh')
  await advance(1)
  expect(fetch).toHaveBeenCalledTimes(2); expect(result.current.freshness).toBe('fresh')
})
it('manual refresh works before six hours and keeps last known data during the request', async () => {
  const { result } = renderHook(() => useWeatherSession(UDUPI)); await flush()
  let resolve
  fetch.mockImplementationOnce(() => new Promise(r => { resolve = r }))
  act(() => { void result.current.refresh() })
  expect(result.current.freshness).toBe('refreshing'); expect(result.current.data).not.toBeNull()
  await act(async () => resolve(reply(body(UDUPI, new Date().toISOString(), 28))))
  expect(result.current.data.current.temperature_c).toBe(28)
  expect(fetch.mock.calls.at(-1)[0]).toBe('/api/weather?latitude=13.34&longitude=74.74')
})
it('fresh visibility/focus/online events and same-coordinate rerenders do not fetch', async () => {
  const { rerender } = renderHook(({ point }) => useWeatherSession(point), { initialProps: { point: UDUPI } }); await flush()
  rerender({ point: { ...UDUPI, name: 'Different label' } })
  hidden(true); hidden(false); event('focus'); event('online'); event('visibilitychange', document)
  expect(fetch).toHaveBeenCalledTimes(1)
})
it('hidden tabs become stale without requests, reactivation refreshes once', async () => {
  const { result } = renderHook(() => useWeatherSession(UDUPI)); await flush()
  hidden(true); await advance(FRESHNESS_MS)
  expect(fetch).toHaveBeenCalledTimes(1)
  // Reactivation rechecks the wall clock even though background timers paused.
  fetch.mockImplementationOnce(() => new Promise(() => {}))
  hidden(false); event('focus'); event('online')
  expect(fetch).toHaveBeenCalledTimes(2); expect(result.current.freshness).toBe('refreshing')
})
it('staleness at the six-hour boundary is independent of loading and current valid time', () => {
  const data = body()
  expect(freshnessOf(data, false, null, BASE.getTime() + FRESHNESS_MS - 1)).toBe('fresh')
  expect(freshnessOf(data, false, null, BASE.getTime() + FRESHNESS_MS)).toBe('stale')
  expect(freshnessOf(data, true, null, BASE.getTime() + FRESHNESS_MS)).toBe('refreshing')
  expect(freshnessOf(null, false, 'Failed', BASE.getTime())).toBe('unavailable')
})
it('deduplicates simultaneous manual, automatic and reactivation requests', async () => {
  fetch.mockImplementation(() => new Promise(() => {}))
  const { result } = renderHook(() => useWeatherSession(UDUPI))
  act(() => { result.current.refresh(); result.current.refresh() })
  event('focus'); event('online'); hidden(false)
  expect(fetch).toHaveBeenCalledTimes(1)
})
it('changing location aborts the old request; an ignored abort cannot overwrite the new point', async () => {
  let resolve
  fetch.mockImplementationOnce(() => new Promise(r => { resolve = r }))
  const { result, rerender } = renderHook(({ point }) => useWeatherSession(point), { initialProps: { point: null } })
  const signal = fetch.mock.calls[0][1].signal
  rerender({ point: UDUPI }); await flush()
  expect(signal.aborted).toBe(true); expect(result.current.data.location).toEqual(UDUPI)
  await act(async () => resolve(reply(body(DEFAULT_POINT, BASE.toISOString(), 99))))
  expect(result.current.data.current.temperature_c).toBe(27)
  expect(result.current.data.location).toEqual(UDUPI)
})
it('failed automatic refresh preserves stale data with bounded 30/60-minute retries, then stops', async () => {
  const { result } = renderHook(() => useWeatherSession(UDUPI)); await flush()
  fetch.mockResolvedValue({ ok: false, json: async () => ({ message: 'Provider unavailable' }) })
  await advance(FRESHNESS_MS)
  expect(result.current.freshness).toBe('stale'); expect(result.current.data.location).toEqual(UDUPI)
  expect(result.current.error).toBe('Provider unavailable')
  for (let i = 0; i < 5; i++) { event('focus'); event('online'); hidden(false) }
  expect(fetch).toHaveBeenCalledTimes(2)
  await advance(RETRY_DELAYS_MS[0]); expect(fetch).toHaveBeenCalledTimes(3)
  await advance(RETRY_DELAYS_MS[1]); expect(fetch).toHaveBeenCalledTimes(4)
  expect(result.current.paused).toBe(true); expect(result.current.retryAt).toBeNull()
  await advance(FRESHNESS_MS * 2); event('focus'); expect(fetch).toHaveBeenCalledTimes(4)
  fetch.mockImplementation(async () => reply(body(UDUPI)))
  act(() => { void result.current.refresh() }); await flush()
  expect(result.current.freshness).toBe('fresh'); expect(result.current.paused).toBe(false)
})
it('a failed early manual refresh is clearly stale even within the age interval', async () => {
  const { result } = renderHook(() => useWeatherSession(null)); await flush()
  fetch.mockRejectedValue(new TypeError('Network interrupted'))
  act(() => { void result.current.refresh() }); await flush()
  expect(result.current.freshness).toBe('stale'); expect(result.current.data).not.toBeNull()
})
it('timeout ends refreshing, keeps same-point data, and clears the request timeout', async () => {
  const { result } = renderHook(() => useWeatherSession(UDUPI)); await flush()
  fetch.mockImplementation((url, { signal }) => new Promise((resolve, reject) => signal.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError')))))
  act(() => { void result.current.refresh() }); await advance(15000)
  expect(result.current.loading).toBe(false); expect(result.current.error).toContain('timed out')
  expect(result.current.freshness).toBe('stale'); expect(vi.getTimerCount()).toBe(1)
})
it.each([null, undefined, 'invalid', '2026-10-08T06:00:00', '2026-10-09T06:00:00Z'])('missing/invalid/future retrieval %s stays unknown/stale without invented clocks or rapid loops', async retrieved => {
  // Preserve missing timestamps literally; fixtures must not supply a clock.
  fetch.mockImplementation(async () => { const response = body(); response.retrieved_at = retrieved; return reply(response) })
  const { result } = renderHook(() => useWeatherSession(null)); await flush()
  expect(retrievalTime(retrieved, Date.now())).toBeNull()
  expect(result.current.freshness).toBe('stale'); expect(result.current.data.retrieved_at).toBe(retrieved)
  event('focus'); event('online'); hidden(false); await advance(60000)
  expect(fetch).toHaveBeenCalledTimes(1)
})
it('stale timestamps returned by provider get a cooldown instead of infinite refresh loops', async () => {
  fetch.mockResolvedValue(reply(body(DEFAULT_POINT, new Date(BASE.getTime() - FRESHNESS_MS).toISOString())))
  const { result } = renderHook(() => useWeatherSession(null)); await flush()
  expect(result.current.freshness).toBe('stale'); await advance(60000)
  expect(fetch).toHaveBeenCalledTimes(1)
})
it('offline startup avoids requests and reconnect attempts the selected point once', async () => {
  vi.spyOn(navigator, 'onLine', 'get').mockReturnValue(false)
  const { result } = renderHook(() => useWeatherSession(UDUPI)); await flush()
  expect(fetch).not.toHaveBeenCalled(); expect(result.current.freshness).toBe('unavailable')
  vi.spyOn(navigator, 'onLine', 'get').mockReturnValue(true); event('online'); await flush()
  expect(fetch).toHaveBeenCalledTimes(1); expect(result.current.data.location).toEqual(UDUPI)
})
it('offline stale data waits until reconnect, fresh reconnection does not fetch', async () => {
  const { result } = renderHook(() => useWeatherSession(null)); await flush()
  vi.spyOn(navigator, 'onLine', 'get').mockReturnValue(false); event('offline')
  await advance(FRESHNESS_MS)
  expect(fetch).toHaveBeenCalledTimes(1); expect(result.current.freshness).toBe('stale')
  vi.spyOn(navigator, 'onLine', 'get').mockReturnValue(true); event('online'); await flush()
  expect(fetch).toHaveBeenCalledTimes(2); expect(result.current.freshness).toBe('fresh')
  event('online'); expect(fetch).toHaveBeenCalledTimes(2)
})
it('location change clears unavailable old data and resets failed-attempt budget', async () => {
  fetch.mockRejectedValueOnce(new TypeError('Offline network'))
  const { result, rerender } = renderHook(({ point }) => useWeatherSession(point), { initialProps: { point: null } }); await flush()
  expect(result.current.freshness).toBe('unavailable')
  rerender({ point: UDUPI }); await flush()
  expect(result.current.freshness).toBe('fresh'); expect(result.current.error).toBeNull()
})
it('unmount aborts request, clears all timers and removes every listener without late updates', async () => {
  const removeDoc = vi.spyOn(document, 'removeEventListener'), removeWindow = vi.spyOn(window, 'removeEventListener')
  let resolve
  fetch.mockImplementation(() => new Promise(r => { resolve = r }))
  const { unmount } = renderHook(() => useWeatherSession(null))
  const signal = fetch.mock.calls[0][1].signal
  unmount(); expect(signal.aborted).toBe(true); expect(vi.getTimerCount()).toBe(0)
  expect(removeDoc.mock.calls.some(([name]) => name === 'visibilitychange')).toBe(true)
  for (const name of ['focus', 'online', 'offline']) expect(removeWindow.mock.calls.some(([type]) => type === name)).toBe(true)
  event('focus'); event('online'); event('visibilitychange', document)
  await act(async () => resolve(reply(body())))
  expect(fetch).toHaveBeenCalledTimes(1); expect(vi.getTimerCount()).toBe(0)
})
it('clock changes are checked on activation without scheduling a duplicate request', async () => {
  const { result } = renderHook(() => useWeatherSession(null)); await flush()
  vi.setSystemTime(new Date(BASE.getTime() + FRESHNESS_MS)); event('focus'); await flush()
  expect(fetch).toHaveBeenCalledTimes(2); expect(result.current.freshness).toBe('fresh')
})

it('pauses background timers on an inactive route and reuses a still-fresh receipt',async()=>{
 const {result,rerender}=renderHook(({enabled})=>useWeatherSession(null,enabled),{initialProps:{enabled:true}})
 await flush();const receipt=result.current.data.retrieved_at
 rerender({enabled:false});expect(vi.getTimerCount()).toBe(0)
 await advance(60*60*1000);event('focus');expect(fetch).toHaveBeenCalledTimes(1)
 rerender({enabled:true});await flush()
 expect(fetch).toHaveBeenCalledTimes(1);expect(result.current.data.retrieved_at).toBe(receipt);expect(result.current.freshness).toBe('fresh')
})
it('an expired receipt is refreshed once upon route reactivation, never while inactive',async()=>{
 const {result,rerender}=renderHook(({enabled})=>useWeatherSession(null,enabled),{initialProps:{enabled:true}})
 await flush();rerender({enabled:false});await advance(FRESHNESS_MS);expect(fetch).toHaveBeenCalledTimes(1)
 rerender({enabled:true});await flush();expect(fetch).toHaveBeenCalledTimes(2);expect(result.current.freshness).toBe('fresh')
})
