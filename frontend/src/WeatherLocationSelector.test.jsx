import React from 'react'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import App from './App.jsx'
import WeatherLocationSelector from './WeatherLocationSelector.jsx'

const state = vi.hoisted(() => ({ map: vi.fn(), tileLayer: vi.fn(), circleMarker: vi.fn(), events: {}, tileEvents: {} }))
vi.mock('leaflet', () => ({ default: state }))
vi.mock('./HistoricalFloodMap.jsx', () => ({ default: () => <div>Historical evidence unchanged</div> }))
vi.mock('./DrainageResearchLayers.jsx', () => ({ default: () => <div>Drainage evidence unchanged</div> }))
const weather = (point = null, temperature = 27) => ({ status: 'partial', message: 'Some values are unavailable.',
  location: point, current: { temperature_c: temperature, humidity_percent: 70, precipitation_mm: 0, interval_seconds: 900, valid_at: '2026-10-08T00:00:00Z', stale: false },
  forecast: [{ date: '2026-10-08', precipitation_mm: 1, temperature_min_c: 20, temperature_max_c: 30 },
    { date: '2026-10-09', precipitation_mm: null, temperature_min_c: 21, temperature_max_c: 31 },
    { date: '2026-10-10', precipitation_mm: 3, temperature_min_c: 21, temperature_max_c: 30 }],
  grid_location: { latitude: 13.35, longitude: 74.75 }, retrieved_at: '2026-10-08T00:01:00Z' })
const reply = body => ({ ok: true, json: async () => body })

beforeEach(() => {
  vi.clearAllMocks(); state.events = {}; state.tileEvents = {}
  const view = { setView: vi.fn().mockReturnThis(), remove: vi.fn(), removeLayer: vi.fn(), on: vi.fn((name, fn) => { state.events[name] = fn }) }
  state.map.mockReturnValue(view)
  state.tileLayer.mockReturnValue({ addTo: vi.fn().mockReturnThis(), on: vi.fn((name, fn) => { state.tileEvents[name] = fn }) })
  state.circleMarker.mockReturnValue({ addTo: vi.fn().mockReturnThis() })
  vi.stubGlobal('fetch', vi.fn(async url => {
    const query = new URL(url, 'http://localhost').searchParams
    const point = query.has('latitude') ? { latitude: Number(query.get('latitude')), longitude: Number(query.get('longitude')) } : null
    return reply(weather(point))
  }))
})
afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.useRealTimers() })

function coordinates(lat = '13.34', lon = '74.74') {
  fireEvent.change(screen.getByLabelText('Weather latitude'), { target: { value: lat } })
  fireEvent.change(screen.getByLabelText('Weather longitude'), { target: { value: lon } })
  fireEvent.click(screen.getByRole('button', { name: 'Get point weather' }))
}

it('keeps Bengaluru default and replaces weather with selected coordinates, preserving nulls and provenance', async () => {
  render(<App />); await screen.findByText('27 °C')
  expect(fetch.mock.calls[0][0]).toBe('/api/weather')
  coordinates()
  await waitFor(() => expect(fetch.mock.calls.at(-1)[0]).toBe('/api/weather?latitude=13.34&longitude=74.74'))
  await screen.findByText('Entered coordinates')
  expect(screen.getByText(/Requested point: 13.34/)).toBeTruthy()
  expect(screen.getByText(/district\/locality identity not verified/)).toBeTruthy()
  expect(screen.getByText('0 mm')).toBeTruthy()
  expect(screen.getAllByText('Unavailable').length).toBeGreaterThan(0)
  expect(screen.getByText(/Flood prediction is not available/)).toBeTruthy()
  expect(screen.getByText('Latitude 13.35°, longitude 74.75°')).toBeTruthy()
})

it('clicking Leaflet selects an exact point and clears old marker on another selection', async () => {
  render(<App />); await screen.findByText('27 °C')
  fireEvent.click(screen.getByRole('button', { name: 'Open weather map' }))
  act(() => state.events.click({ latlng: { lat: 13.34, lng: 74.74 } }))
  await waitFor(() => expect(fetch.mock.calls.at(-1)[0]).toContain('latitude=13.34&longitude=74.74'))
  expect(state.circleMarker.mock.calls.at(-1)[0]).toEqual([13.34, 74.74])
  expect(state.map.mock.results[0].value.removeLayer).toHaveBeenCalled()
  act(() => state.tileEvents.tileerror())
  expect(screen.getByText(/Background tiles are unavailable/)).toBeTruthy()
})

it('GPS is requested only after a click and has permission-denied/manual fallback', () => {
  const gps = vi.fn((success, failure) => failure({ code: 1 }))
  vi.stubGlobal('navigator', { geolocation: { getCurrentPosition: gps } })
  const selected = vi.fn(); render(<WeatherLocationSelector onSelect={selected} />)
  expect(gps).not.toHaveBeenCalled()
  fireEvent.click(screen.getByRole('button', { name: 'Use my GPS location' }))
  expect(screen.getByRole('alert').textContent).toContain('Location permission denied')
  expect(selected).not.toHaveBeenCalled()
  coordinates(); expect(selected).toHaveBeenCalledWith({ name: 'Entered coordinates', latitude: 13.34, longitude: 74.74 })
})

it('GPS preserves device uncertainty and ignores callbacks after a newer manual selection', () => {
  let success
  vi.stubGlobal('navigator', { geolocation: { getCurrentPosition: vi.fn(fn => { success = fn }) } })
  const selected = vi.fn(); render(<WeatherLocationSelector onSelect={selected} />)
  fireEvent.click(screen.getByRole('button', { name: 'Use my GPS location' }))
  act(() => success({ coords: { latitude: 13.34, longitude: 74.74, accuracy: 50 } }))
  expect(selected).toHaveBeenLastCalledWith({ name: 'GPS-selected point', latitude: 13.34, longitude: 74.74, accuracy_m: 50 })
  fireEvent.click(screen.getByRole('button', { name: 'Use my GPS location' }))
  coordinates('14', '75')
  act(() => success({ coords: { latitude: 13, longitude: 74, accuracy: 50 } }))
  expect(selected).toHaveBeenLastCalledWith({ name: 'Entered coordinates', latitude: 14, longitude: 75 })
})

it('coordinate validation rejects blank values and zero remains a real coordinate', () => {
  const selected = vi.fn(); render(<WeatherLocationSelector onSelect={selected} />)
  fireEvent.change(screen.getByLabelText('Weather latitude'), { target: { value: '' } })
  fireEvent.submit(screen.getByRole('button', { name: 'Get point weather' }).closest('form'))
  expect(screen.getByRole('alert')).toBeTruthy(); expect(selected).not.toHaveBeenCalled()
  coordinates('0', '0'); expect(selected).toHaveBeenLastCalledWith({ name: 'Entered coordinates', latitude: 0, longitude: 0 })
})

it('failed point request clears old readings and refresh retains the requested point', async () => {
  render(<App />); await screen.findByText('27 °C')
  fetch.mockResolvedValue({ ok: false, json: async () => ({ status: 'unavailable', message: 'Provider unavailable' }) })
  coordinates()
  expect((await screen.findByRole('alert')).textContent).toContain('Provider unavailable')
  expect(screen.queryByText('27 °C')).toBeNull()
  fireEvent.click(screen.getByRole('button', { name: 'Refresh weather' }))
  await waitFor(() => expect(fetch.mock.calls.at(-1)[0]).toContain('latitude=13.34&longitude=74.74'))
})

it('mismatched returned point is rejected rather than displaying another location', async () => {
  render(<App />); await screen.findByText('27 °C')
  fetch.mockResolvedValue(reply(weather({ latitude: 99, longitude: 75 })))
  coordinates()
  expect((await screen.findByRole('alert')).textContent).toContain('does not match the selected location')
  expect(screen.queryByText('27 °C')).toBeNull()
})

it('late old response cannot overwrite a newer selected point', async () => {
  let finishOld
  fetch.mockImplementationOnce(() => new Promise(resolve => { finishOld = resolve }))
  render(<App />); coordinates()
  await screen.findByText('27 °C')
  await act(async () => { finishOld(reply(weather(null, 99))); await Promise.resolve() })
  expect(screen.queryByText('99 °C')).toBeNull()
  expect(screen.getByText('27 °C')).toBeTruthy()
})

it('reset restores Bengaluru coordinates through the same API flow', async () => {
  render(<App />); await screen.findByText('27 °C'); coordinates()
  await screen.findByText('Entered coordinates')
  fireEvent.click(screen.getByRole('button', { name: 'Reset to Bengaluru' }))
  await waitFor(() => expect(fetch.mock.calls.at(-1)[0]).toContain('latitude=12.9767936&longitude=77.590082'))
})

it('weather timeout ends loading and keeps prediction unavailable', async () => {
  vi.useFakeTimers()
  fetch.mockImplementation((url, options) => new Promise((resolve, reject) => options.signal.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError')))))
  render(<App />)
  await act(async () => { await vi.advanceTimersByTimeAsync(15000) })
  expect(screen.getByRole('alert').textContent).toContain('timed out')
  expect(screen.getByRole('button', { name: 'Refresh weather' }).disabled).toBe(false)
})


it('wrapped basemap longitude becomes the same valid WGS84 point, without a guessed locality', async () => {
  render(<App />); await screen.findByText('27 °C')
  fireEvent.click(screen.getByRole('button', { name: 'Open weather map' }))
  act(() => state.events.click({ latlng: { lat: 13, lng: 435 } }))
  await waitFor(() => expect(fetch.mock.calls.at(-1)[0]).toContain('latitude=13&longitude=75'))
  expect(state.circleMarker.mock.calls.at(-1)[0]).toEqual([13, 75])
})


it('repeated reset to the same reference reloads weather instead of leaving a cleared loading state', async () => {
  render(<App />); await screen.findByText('27 °C')
  fireEvent.click(screen.getByRole('button', { name: 'Reset to Bengaluru' }))
  await screen.findByText('27 °C')
  const count = fetch.mock.calls.length
  fireEvent.click(screen.getByRole('button', { name: 'Reset to Bengaluru' }))
  await waitFor(() => expect(fetch.mock.calls.length).toBe(count + 1))
  await screen.findByText('27 °C')
  expect(screen.getByRole('button', { name: 'Refresh weather' }).disabled).toBe(false)
})
