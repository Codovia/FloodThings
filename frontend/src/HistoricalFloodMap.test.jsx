import React from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import HistoricalFloodMap from './HistoricalFloodMap.jsx'
import App from './App.jsx'

const leaflet = vi.hoisted(() => ({ map: vi.fn(), tileLayer: vi.fn(), geoJSON: vi.fn(), circleMarker: vi.fn() }))
vi.mock('leaflet', () => ({ default: leaflet }))

const boundary = { type: 'Feature', properties: { shapeID: 'controlled-test-boundary' }, geometry: { type: 'Polygon', coordinates: [[[74,13],[75,13],[75,14],[74,13]]] } }
const events = [
  { event_id: 2728, start_date: '2005-09-14', end_date_inclusive: '2005-09-30', qualified_pixel_count: 1, retrieved_at: '2026-10-03T00:00:00Z', image_id: 'controlled-test-source-2728' },
  { event_id: 3551, start_date: '2009-09-25', end_date_inclusive: '2009-10-12', qualified_pixel_count: 1, retrieved_at: '2026-10-03T00:00:00Z', image_id: 'controlled-test-source-3551' },
]
const geometry = (eventId) => ({ type: 'FeatureCollection', features: [{ type: 'Feature', properties: { event_id: eventId, clear_views: 2 },
  geometry: { type: 'Polygon', coordinates: [[[74.6,13.5],[74.602,13.5],[74.602,13.502],[74.6,13.5]]] } }] })
const reply = (body, ok = true) => Promise.resolve({ ok, json: async () => body })
const fixtureFetch = (url) => {
  if (url === '/api/historical-floods') return reply({ status: 'available', events, boundary })
  if (url.startsWith('/api/historical-floods/')) {
    const id = Number(url.split('/').at(-1))
    return reply({ status: 'available', event: events.find(e => e.event_id === id), floodwater: geometry(id) })
  }
  throw new Error(`Unexpected test request: ${url}`)
}

beforeEach(() => {
  window.history.replaceState(null,'','/weather')
  vi.clearAllMocks()
  leaflet.circleMarker.mockReturnValue({addTo:vi.fn().mockReturnThis()})
  leaflet.map.mockReturnValue({ setView:vi.fn().mockReturnThis(), on:vi.fn(), fitBounds: vi.fn(), removeLayer: vi.fn(), remove: vi.fn() })
  leaflet.tileLayer.mockReturnValue({ addTo: vi.fn().mockReturnThis(), on: vi.fn() })
  leaflet.geoJSON.mockImplementation(() => ({ addTo: vi.fn().mockReturnThis(), getBounds: vi.fn().mockReturnValue({}) }))
  vi.stubGlobal('fetch', vi.fn(fixtureFetch))
})
afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.useRealTimers() })

describe('historical evidence display', () => {
  it('renders the event window, attribution and original polygons through Leaflet', async () => {
    render(<HistoricalFloodMap />)
    await screen.findByText(/Source image: controlled-test-source-2728/)
    expect(screen.getByText(/not current flooding/)).toBeTruthy()
    expect(screen.getByRole('link', { name: 'CC BY-NC 4.0' }).href).toContain('creativecommons.org/licenses/by-nc/4.0')
    expect(screen.getByRole('region', { name: /Historical satellite floodwater/ })).toBeTruthy()
    await waitFor(() => expect(leaflet.geoJSON.mock.calls.some(([data]) => JSON.stringify(data) === JSON.stringify(geometry(2728)))).toBe(true))
    expect(screen.getByRole('combobox').options).toHaveLength(2)
  })

  it('selects 3551 and replaces the geometry without using centroids or circles', async () => {
    render(<HistoricalFloodMap />)
    await screen.findByText(/Source image: controlled-test-source-2728/)
    fireEvent.change(screen.getByRole('combobox'), { target: { value: '3551' } })
    await screen.findByText(/Source image: controlled-test-source-3551/)
    const drawn = leaflet.geoJSON.mock.calls.filter(([data]) => data.type === 'FeatureCollection')
    expect(drawn.at(-1)[0]).toEqual(geometry(3551))
    expect(screen.getByText(/Recorded window/).textContent).toContain('2009')
    expect(leaflet.map.mock.results[0].value.removeLayer).toHaveBeenCalled()
  })

  it('shows unavailable evidence without drawing a replacement map', async () => {
    vi.mocked(fetch).mockResolvedValue({ ok: false, json: async () => ({ status: 'unavailable', message: 'Missing spatial dataset' }) })
    render(<HistoricalFloodMap />)
    expect((await screen.findByRole('alert')).textContent).toContain('No flood-absence conclusion')
    expect(leaflet.map).not.toHaveBeenCalled()
    expect(screen.getByRole('link', { name: 'CC BY-NC 4.0' })).toBeTruthy()
  })

  it('clears previous evidence when a new event request fails', async () => {
    vi.mocked(fetch).mockImplementation(url => url.endsWith('/3551') ? reply({ status: 'unavailable', message: 'Missing geometry' }, false) : fixtureFetch(url))
    render(<HistoricalFloodMap />)
    await screen.findByText(/Source image: controlled-test-source-2728/)
    fireEvent.change(screen.getByRole('combobox'), { target: { value: '3551' } })
    await screen.findByRole('alert')
    expect(screen.queryByText(/Source image:/)).toBeNull()
    expect(leaflet.map.mock.results[0].value.removeLayer).toHaveBeenCalled()
  })

  it('rejects geometry returned for the wrong event', async () => {
    vi.mocked(fetch).mockImplementation(url => url.endsWith('/2728') ? reply({ status: 'available', event: events[1], floodwater: geometry(3551) }) : fixtureFetch(url))
    render(<HistoricalFloodMap />)
    expect((await screen.findByRole('alert')).textContent).toContain('inconsistent')
    expect(leaflet.geoJSON.mock.calls.some(([data]) => data.type === 'FeatureCollection')).toBe(false)
  })

  it('ends the loading state with an explicit timeout', async () => {
    vi.useFakeTimers()
    vi.mocked(fetch).mockImplementation((url, options) => new Promise((resolve, reject) => {
      options.signal.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError')))
    }))
    render(<HistoricalFloodMap />)
    await act(async () => { await vi.advanceTimersByTimeAsync(15000) })
    expect(screen.getByRole('alert').textContent).toContain('timed out')
    expect(screen.queryByText('Loading historical flood geometry…')).toBeNull()
    expect(leaflet.map).not.toHaveBeenCalled()
  })

  it('preserves the weather dashboard while adding historical evidence', async () => {
    vi.mocked(fetch).mockImplementation(url => url === '/api/weather' ? reply({ status: 'available',
      current: { temperature_c: 27, humidity_percent: 70, precipitation_mm: 1, interval_seconds: 900, valid_at: '2026-10-03T00:00:00Z', stale: false },
      forecast: [{ date: '2026-10-03', precipitation_mm: 2, temperature_min_c: 22, temperature_max_c: 28 }],
      grid_location: { latitude: 12.97, longitude: 77.59 }, retrieved_at: '2026-10-03T00:00:00Z' }) : fixtureFetch(url))
    render(<App />)
    await screen.findByText('27 °C')
    fireEvent.click(screen.getByRole('link', {name:'Flood Map',exact:true}))
    await screen.findByText(/Source image: controlled-test-source-2728/)
    fireEvent.click(screen.getByRole('link', {name:'Weather & AI',exact:true}))
    expect(screen.getByText('27 °C')).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Refresh weather' })).toBeTruthy()
    expect(screen.getByRole('link', { name: 'Open-Meteo' })).toBeTruthy()
  })
})
