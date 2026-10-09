import React from 'react'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import LocationDirectorySelector from './LocationDirectorySelector.jsx'
import App from './App.jsx'
import expandedDirectory from '../../data/reference/karnataka_location_directory_v2/directory.json'

const mapState = vi.hoisted(() => ({ map: vi.fn(), tileLayer: vi.fn(), circleMarker: vi.fn() }))
vi.mock('leaflet', () => ({ default: mapState }))
vi.mock('./HistoricalFloodMap.jsx', () => ({ default: () => <div>Historical evidence</div> }))
vi.mock('./DrainageResearchLayers.jsx', () => ({ default: () => <div>Research layers</div> }))
const districts = [{ id: 'nic:udupi.nic.in', name: 'Udupi', navigation_bounds: [[13,74],[14,75]] }, { id: 'nic:other.nic.in', name: 'Other district', navigation_bounds: null }]
const places = [1,2].map((id, i) => ({ id: `osm:node:${id}`, name: 'Duplicate fixture', district_id: districts[0].id, selectable: true, coordinate_status: 'verified_osm_place_point',
  coordinates: { latitude: [13.2,13.4][i], longitude: [74.5,74.7][i] }, coordinate_source: { license: 'ODbL 1.0', url: `https://www.openstreetmap.org/node/${id}` }, association_source_url: 'https://udupi.nic.in/en/municipal-administration/' }))
const missing = { id: 'missing', name: 'Name only', district_id: districts[0].id, selectable: false, coordinates: null, coordinate_status: 'unavailable' }
const response = (items) => ({ ok: true, json: async () => ({ status: 'available', items, total: items.length }) })
const weather = point => ({ status: 'available', location: point, retrieved_at: new Date().toISOString(), current: { temperature_c: 27, valid_at: new Date().toISOString(), interval_seconds: 900 },
  forecast: Array.from({ length: 7 }, (_, i) => ({ date: `2026-10-${String(i+8).padStart(2,'0')}`, temperature_max_c: 30, temperature_min_c: 20, precipitation_mm: 1 })), grid_location: { latitude: 13.21, longitude: 74.51 } })
const open = () => fireEvent.click(screen.getByRole('button', { name: 'Search districts and localities' }))
const district = async (id = districts[0].id) => { await waitFor(() => expect(screen.getByLabelText('Karnataka district').disabled).toBe(false)); fireEvent.change(screen.getByLabelText('Karnataka district'), { target: { value: id } }) }

beforeEach(() => {
  vi.clearAllMocks()
  mapState.map.mockReturnValue({ setView: vi.fn().mockReturnThis(), fitBounds: vi.fn(), remove: vi.fn(), removeLayer: vi.fn(), on: vi.fn() })
  mapState.tileLayer.mockReturnValue({ addTo: vi.fn().mockReturnThis(), on: vi.fn() })
  mapState.circleMarker.mockReturnValue({ addTo: vi.fn().mockReturnThis() })
  vi.stubGlobal('fetch', vi.fn(async url => {
    const parsed = new URL(url, 'http://localhost')
    if (parsed.pathname === '/api/locations/districts') return response(districts)
    if (parsed.pathname === '/api/locations/search') return response([{ ...districts[0], kind: 'district' }, { ...places[0], kind: 'locality' }])
    if (parsed.pathname === '/api/locations/localities') return response(parsed.searchParams.get('district_id') === districts[0].id ? [...places, missing] : [])
    return { ok: true, json: async () => weather(parsed.searchParams.has('latitude') ? { latitude: +parsed.searchParams.get('latitude'), longitude: +parsed.searchParams.get('longitude') } : null) }
  }))
})
afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals(); vi.useRealTimers() })

it('loads directory only on user action and exposes labelled controls and provenance', async () => {
  render(<LocationDirectorySelector onChoose={vi.fn()} onDistrict={vi.fn()} />)
  expect(fetch).not.toHaveBeenCalled(); open(); await screen.findByRole('option', { name: 'Udupi' })
  expect(screen.getByLabelText('Search districts or localities')).toBeTruthy()
  expect(screen.getByRole('link', { name: /OpenStreetMap contributors/ }).getAttribute('href')).toContain('copyright')
})
it('district selection filters localities and navigates without creating a weather point', async () => {
  const choose = vi.fn(), navigate = vi.fn()
  render(<LocationDirectorySelector onChoose={choose} onDistrict={navigate} />); open(); await district()
  await screen.findByRole('button', { name: /Name only/ })
  expect(navigate).toHaveBeenCalledWith(districts[0]); expect(choose).not.toHaveBeenCalled()
  expect(screen.getByRole('button', { name: /Name only/ }).disabled).toBe(true)
})
it('duplicate names remain separate source IDs and exact coordinates', async () => {
  const choose = vi.fn(); render(<LocationDirectorySelector onChoose={choose} onDistrict={vi.fn()} />); open(); await district()
  const buttons = await screen.findAllByRole('button', { name: /Duplicate fixture/ })
  expect(buttons[0].getAttribute('aria-label')).not.toBe(buttons[1].getAttribute('aria-label'))
  fireEvent.click(buttons[0]); fireEvent.click(buttons[1])
  expect(choose.mock.calls.map(([p]) => p.locality_id)).toEqual(['osm:node:1', 'osm:node:2'])
  expect(choose.mock.calls[1][0].latitude).toBe(13.4)
})
it('district without geometry or localities reports unavailable coverage', async () => {
  render(<LocationDirectorySelector onChoose={vi.fn()} onDistrict={vi.fn()} />); open(); await district(districts[1].id)
  expect((await screen.findByRole('status', { name: 'District locality results' })).textContent).toContain('No verified localities')
  expect(screen.getByText(/representative point are unavailable/)).toBeTruthy()
})
it('search is debounced, bounded and district/locality result names are accessible', async () => {
  render(<LocationDirectorySelector onChoose={vi.fn()} onDistrict={vi.fn()} />); open(); await district()
  fireEvent.change(screen.getByLabelText('Search districts or localities'), { target: { value: 'Udupi' } })
  await screen.findByRole('button', { name: 'Udupi — District · filter localities' })
  expect(fetch.mock.calls.some(([url]) => url === '/api/locations/search?q=Udupi&limit=20')).toBe(true)
})
it('search empty response and failed API permit honest retry without substituting a place', async () => {
  fetch.mockImplementation(async url => url.includes('/search?') ? response([]) : response(districts))
  render(<LocationDirectorySelector onChoose={vi.fn()} onDistrict={vi.fn()} />); open(); await district()
  fireEvent.change(screen.getByLabelText('Search districts or localities'), { target: { value: 'Absent' } })
  await screen.findByText(/No matching places/)
  fetch.mockResolvedValue({ ok: false, json: async () => ({ detail: 'Directory unavailable' }) })
  fireEvent.click(screen.getByRole('button', { name: 'Close place search' })); open()
  expect((await screen.findByRole('alert', { name: 'Location directory error' })).textContent).toContain('Directory unavailable')
  fetch.mockResolvedValue(response(districts)); fireEvent.click(screen.getByRole('button', { name: 'Retry location search' }))
  await waitFor(() => expect(screen.queryByRole('alert')).toBeNull())
})
it('keyboard opens search, navigates native district control and selects a locality without traps', async () => {
  const user = userEvent.setup(), choose = vi.fn()
  render(<LocationDirectorySelector onChoose={choose} onDistrict={vi.fn()} />)
  await user.tab(); expect(document.activeElement.textContent).toBe('Search districts and localities'); await user.keyboard('{Enter}')
  await screen.findByRole('option', { name: 'Udupi' }); await user.selectOptions(screen.getByLabelText('Karnataka district'), districts[0].id)
  const button = (await screen.findAllByRole('button', { name: /Duplicate fixture/ }))[0]
  button.focus(); await user.keyboard('{Enter}'); expect(choose).toHaveBeenCalledTimes(1)
  await user.tab(); expect(document.activeElement).not.toBe(button)
})
it('timeout is bounded and cancelled requests do not update after closing or unmount', async () => {
  vi.useFakeTimers(); const signals = []
  fetch.mockImplementation((url, options) => new Promise((resolve, reject) => { signals.push(options.signal); options.signal.addEventListener('abort', () => reject(new DOMException('Aborted','AbortError'))) }))
  const { unmount } = render(<LocationDirectorySelector onChoose={vi.fn()} onDistrict={vi.fn()} />); open()
  await act(async () => { await vi.advanceTimersByTimeAsync(10000) })
  expect(screen.getByRole('alert', { name: 'Location directory error' }).textContent).toContain('timed out')
  fireEvent.click(screen.getByRole('button', { name: 'Retry location search' })); unmount()
  expect(signals.every(signal => signal.aborted)).toBe(true); expect(vi.getTimerCount()).toBe(0)
})
it('late directory responses cannot replace the newer district locality list', async () => {
  let finish
  fetch.mockImplementation(async url => url.includes('localities?district_id=nic%3Audupi') ? new Promise(resolve => { finish = resolve }) : response(url.includes('/districts') ? districts : []))
  render(<LocationDirectorySelector onChoose={vi.fn()} onDistrict={vi.fn()} />); open(); await district(); await district(districts[1].id)
  await screen.findByText(/No verified localities/)
  await act(async () => finish(response(places)))
  expect(screen.queryByRole('button', { name: /Duplicate fixture/ })).toBeNull()
})
it('locality selection recenters map and changes weather; district navigation makes no weather request', async () => {
  render(<App />); await screen.findByText('27 °C'); open(); await district()
  await screen.findAllByRole('button', { name: /Duplicate fixture/ })
  expect(fetch.mock.calls.filter(([url]) => url.startsWith('/api/weather'))).toHaveLength(1)
  expect(mapState.map.mock.results[0].value.fitBounds).toHaveBeenCalledWith(districts[0].navigation_bounds, { animate: false })
  fireEvent.click(screen.getAllByRole('button', { name: /Duplicate fixture/ })[0])
  await waitFor(() => expect(fetch.mock.calls.some(([url]) => url === '/api/weather?latitude=13.2&longitude=74.5')).toBe(true))
  await screen.findByText('Duplicate fixture, Udupi')
  expect(mapState.map.mock.results[0].value.setView).toHaveBeenLastCalledWith([13.2,74.5],12, { animate: false })
  expect(screen.getByRole('list', { name: 'Daily weather forecasts' }).children).toHaveLength(7)
  expect(screen.getByRole('status', { name: 'Weather data freshness' }).textContent).toContain('Fresh')
  expect(screen.getByText(/Point weather, not locality-wide/)).toBeTruthy()
})
it('switching localities during weather request prevents the older point overwriting the new one', async () => {
  let finishOld
  const normal = fetch.getMockImplementation()
  fetch.mockImplementation(url => url === '/api/weather?latitude=13.2&longitude=74.5' ? new Promise(resolve => { finishOld = resolve }) : normal(url))
  render(<App />); await screen.findByText('27 °C'); open(); await district()
  const buttons = await screen.findAllByRole('button', { name: /Duplicate fixture/ }); fireEvent.click(buttons[0]); fireEvent.click(buttons[1])
  await waitFor(() => expect(screen.getByText(/Requested point: 13.4/)).toBeTruthy())
  await screen.findByText('27 °C')
  await act(async () => finishOld({ ok: true, json: async () => ({ ...weather({latitude:13.2,longitude:74.5}), current: {temperature_c:99} }) }))
  expect(screen.queryByText('99 °C')).toBeNull()
  expect(screen.getByText(/Requested point: 13.4/)).toBeTruthy()
})
it('restricted coordinate provenance cannot trigger weather even if a malformed result claims selectable', async () => {
  const choose = vi.fn(); const malformed = { ...places[0], coordinate_source: { license: 'restricted SOI' } }
  fetch.mockImplementation(async url => response(url.includes('/districts') ? districts : [malformed]))
  render(<LocationDirectorySelector onChoose={choose} onDistrict={vi.fn()} />); open(); await district()
  const button = await screen.findByRole('button', { name: /Duplicate fixture/ })
  expect(button.disabled).toBe(true); fireEvent.click(button)
  expect(choose).not.toHaveBeenCalled()
})

function expandedResponses() {
  const data = expandedDirectory
  fetch.mockImplementation(async url => {
    const parsed = new URL(url, 'http://localhost')
    if (parsed.pathname === '/api/locations/districts') return { ok: true, json: async () => ({ status: 'available', items: data.districts, total: 31, coverage: data.coverage, dataset_version: data.version }) }
    if (parsed.pathname === '/api/locations/localities') return response(data.localities.filter(r => r.district_id === parsed.searchParams.get('district_id')))
    return { ok: true, json: async () => weather(parsed.searchParams.has('latitude') ? { latitude: +parsed.searchParams.get('latitude'), longitude: +parsed.searchParams.get('longitude') } : null) }
  })
  return data
}

it('expanded source directory displays actual coverage, enables Kundapur and explains disabled Kaup', async () => {
  expandedResponses(); const choose = vi.fn()
  render(<LocationDirectorySelector onChoose={choose} onDistrict={vi.fn()} />); open(); await district()
  expect(screen.getByText(/5 selectable mapped localities across 2 districts/)).toBeTruthy()
  const kundapur = await screen.findByRole('button', { name: /^Kundapur —/ })
  fireEvent.click(kundapur)
  expect(choose.mock.calls[0][0]).toMatchObject({locality_id:'udupi-admin:municipality:kundapur',latitude:13.6250993,longitude:74.6915722})
  const unavailable = screen.getByRole('button', { name: /^Kaup —/ })
  expect(unavailable.disabled).toBe(true)
  expect(document.getElementById(unavailable.getAttribute('aria-describedby')).textContent).toContain('not reviewed')
})

it('Mangaluru selection uses its retained point and association, preserving seven days and map recentering', async () => {
  expandedResponses(); render(<App />); await screen.findByText('27 °C'); open(); await district('nic:dk.nic.in')
  fireEvent.click(await screen.findByRole('button',{name:/^Mangaluru — Dakshina Kannada/}))
  await screen.findByRole('heading',{name:'Mangaluru, Dakshina Kannada'})
  await waitFor(()=>expect(fetch.mock.calls.some(([url])=>url==='/api/weather?latitude=12.8698101&longitude=74.8430082')).toBe(true))
  expect(mapState.map.mock.results[0].value.setView).toHaveBeenLastCalledWith([12.8698101,74.8430082],12,{animate:false})
  expect(screen.getByRole('list',{name:'Daily weather forecasts'}).children).toHaveLength(7)
  expect(screen.getByRole('status',{name:'Weather data freshness'}).textContent).toContain('Fresh')
  expect(screen.getByRole('link',{name:'Dakshina Kannada district association'}).getAttribute('href')).toBe('https://dk.nic.in/en/municipal-administration/')
})
