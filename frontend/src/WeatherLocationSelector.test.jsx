import React from 'react'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { DEFAULT_POINT } from './WeatherLocationSelector.jsx'
import WeatherLocationSelector from './WeatherLocationSelector.jsx'

const state = vi.hoisted(() => ({ map: vi.fn(), tileLayer: vi.fn(), circleMarker: vi.fn(), events: {}, tileEvents: {} }))
vi.mock('leaflet', () => ({ default: state }))
const reply = body => ({ ok: true, json: async () => body })

beforeEach(() => {
  vi.clearAllMocks(); state.events = {}; state.tileEvents = {}
  const view = { setView: vi.fn().mockReturnThis(), remove: vi.fn(), removeLayer: vi.fn(), on: vi.fn((name, fn) => { state.events[name] = fn }) }
  state.map.mockReturnValue(view)
  state.tileLayer.mockReturnValue({ addTo: vi.fn().mockReturnThis(), on: vi.fn((name, fn) => { state.tileEvents[name] = fn }) })
  state.circleMarker.mockReturnValue({ addTo: vi.fn().mockReturnThis() })
  // Only the place search behind "Change location" talks to the server; it is not opened in these tests.
  vi.stubGlobal('fetch', vi.fn(async () => reply({ status: 'unavailable', items: [], total: 0 })))
})
afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.useRealTimers() })

// Place controls are in the "Change location" popup on compact layouts.
const resetButton = () => { if (!screen.queryByRole('button', { name: 'Reset to Bengaluru' })) fireEvent.click(screen.getByRole('button', { name: 'Change location' })); return screen.getByRole('button', { name: 'Reset to Bengaluru' }) }

function coordinates(lat = '13.34', lon = '74.74') {
  const editor=screen.queryByText('Change location')?.closest('details');if(editor&&!editor.open)fireEvent.click(screen.getByText('Change location'))
  if (!screen.queryByRole('region', {name:'Weather location selection map'})) fireEvent.click(screen.getByRole('button',{name:'Open weather map'}))
  act(()=>state.events.click({latlng:{lat:Number(lat),lng:Number(lon)}}))
}

// Weather loading for a chosen point (failures, late answers, timeouts, mismatched points) is tested in
// useWeatherSession.test.jsx and Home's WeatherStrip; these tests cover choosing the point.
it('clicking the map selects the exact point, redraws the marker and reports missing background tiles', () => {
  const selected = vi.fn()
  const { rerender } = render(<WeatherLocationSelector point={DEFAULT_POINT} onSelect={selected} />)
  coordinates()
  expect(selected).toHaveBeenCalledWith({ name: 'Selected map point', kind: 'map', latitude: 13.34, longitude: 74.74 })
  rerender(<WeatherLocationSelector point={{ name: 'Selected map point', kind: 'map', latitude: 13.34, longitude: 74.74 }} onSelect={selected} />)
  expect(state.circleMarker.mock.calls.at(-1)[0]).toEqual([13.34, 74.74])
  expect(state.map.mock.results[0].value.removeLayer).toHaveBeenCalled()
  act(() => state.tileEvents.tileerror())
  expect(screen.getByText(/Background tiles are unavailable/)).toBeTruthy()
})

it('a wrapped basemap longitude becomes the same valid WGS84 point, without a guessed locality', () => {
  const selected = vi.fn(); render(<WeatherLocationSelector point={DEFAULT_POINT} onSelect={selected} />)
  coordinates('13', '435')
  expect(selected).toHaveBeenCalledWith({ name: 'Selected map point', kind: 'map', latitude: 13, longitude: 75 })
})

it('reset chooses the Bengaluru reference point again, also when it is already selected', () => {
  const selected = vi.fn(); render(<WeatherLocationSelector point={DEFAULT_POINT} onSelect={selected} />)
  fireEvent.click(resetButton()); fireEvent.click(resetButton())
  expect(selected).toHaveBeenCalledTimes(2); expect(selected).toHaveBeenLastCalledWith(DEFAULT_POINT)
})

it('GPS is requested only after a click and has permission-denied/map fallback', () => {
  const gps = vi.fn((success, failure) => failure({ code: 1 }))
  vi.stubGlobal('navigator', { geolocation: { getCurrentPosition: gps } })
  const selected = vi.fn(); render(<WeatherLocationSelector onSelect={selected} />)
  expect(gps).not.toHaveBeenCalled()
  fireEvent.click(screen.getByRole('button', { name: 'Use my GPS location' }))
  expect(screen.getByRole('alert').textContent).toContain('Location permission denied')
  expect(selected).not.toHaveBeenCalled()
  coordinates(); expect(selected).toHaveBeenCalledWith({ name: 'Selected map point', kind: 'map', latitude: 13.34, longitude: 74.74 })
})

it('GPS preserves device uncertainty and ignores callbacks after a newer map selection', () => {
  let success
  vi.stubGlobal('navigator', { geolocation: { getCurrentPosition: vi.fn(fn => { success = fn }) } })
  const selected = vi.fn(); render(<WeatherLocationSelector onSelect={selected} />)
  fireEvent.click(screen.getByRole('button', { name: 'Use my GPS location' }))
  act(() => success({ coords: { latitude: 13.34, longitude: 74.74, accuracy: 50 } }))
  expect(selected).toHaveBeenLastCalledWith({ name: 'GPS-selected point', kind: 'gps', latitude: 13.34, longitude: 74.74, accuracy_m: 50 })
  fireEvent.click(screen.getByRole('button', { name: 'Use my GPS location' }))
  coordinates('14', '75')
  act(() => success({ coords: { latitude: 13, longitude: 74, accuracy: 50 } }))
  expect(selected).toHaveBeenLastCalledWith({ name: 'Selected map point', kind: 'map', latitude: 14, longitude: 75 })
})

it('public coordinate fields are absent and invalid GPS is rejected while zero is valid',()=>{
 let success;vi.stubGlobal('navigator',{geolocation:{getCurrentPosition:vi.fn(fn=>{success=fn})}})
 const selected=vi.fn();render(<WeatherLocationSelector onSelect={selected}/>);
 expect(screen.queryByLabelText('Weather latitude')).toBeNull();expect(screen.queryByLabelText('Weather longitude')).toBeNull()
 fireEvent.click(screen.getByRole('button',{name:'Use my GPS location'}));act(()=>success({coords:{latitude:91,longitude:75}}));expect(screen.getByRole('alert')).toBeTruthy();expect(selected).not.toHaveBeenCalled()
 fireEvent.click(screen.getByRole('button',{name:'Use my GPS location'}));act(()=>success({coords:{latitude:0,longitude:0,accuracy:50}}));expect(selected).toHaveBeenCalledWith({name:'GPS-selected point',kind:'gps',latitude:0,longitude:0,accuracy_m:50})
})

it('compact name controls start collapsed and point selection uses the map',()=>{
 const selected=vi.fn();render(<WeatherLocationSelector compact onSelect={selected}/>);
 expect(screen.queryByRole('dialog')).toBeNull()
 expect(screen.queryByRole('button',{name:'Get point weather'})).toBeNull()
 fireEvent.click(screen.getByRole('button',{name:'Change location'}));expect(screen.getByRole('dialog',{name:'Change location'})).toBeTruthy()
 fireEvent.click(screen.getByRole('button',{name:'Close'}));coordinates('14','75');expect(selected).toHaveBeenCalledWith({name:'Selected map point',kind:'map',latitude:14,longitude:75})
})
it('home preview shows the real selectable point map without showing coordinate controls',()=>{
 render(<WeatherLocationSelector compact overview onSelect={vi.fn()}/>);
 expect(screen.getByRole('region',{name:'Weather location selection map'})).toBeTruthy()
 expect(screen.queryByRole('button',{name:'Get point weather'})).toBeNull()
 expect(state.tileLayer.mock.calls[0][1].referrerPolicy).toBe('origin')
})
