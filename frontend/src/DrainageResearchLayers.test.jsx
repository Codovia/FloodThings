import React from 'react'
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import DrainageResearchLayers from './DrainageResearchLayers.jsx'

const leaflet = vi.hoisted(() => ({ map: vi.fn(), tileLayer: vi.fn(), geoJSON: vi.fn(), imageOverlay: vi.fn() }))
vi.mock('leaflet', () => ({ default: leaflet }))
const DEM = 'COPERNICUS/DEM/GLO30_2024_1', LAND = 'ESA/WorldCover/v200'
const fixture = () => ({ status: 'available', dataset_version: 'udupi_drainage_gis_v1',
  study_area: { type: 'Feature', properties: { official_municipal_boundary: false, anchor_osm_node_id: 245620117 },
    geometry: { type: 'Polygon', coordinates: [[[74.73,13.33],[74.76,13.33],[74.76,13.35],[74.73,13.33]]] } },
  finished_at: '2026-10-03T00:00:00Z',
  layers: Object.fromEntries(['elevation', 'slope', 'land_cover'].map(key => [key, { status: 'available',
    source_id: key === 'land_cover' ? LAND : DEM, url: `/api/drainage-research/layers/${key}.png`,
    preview_bounds: [[13.33,74.73],[13.35,74.76]], resolution_m: key === 'land_cover' ? 10 : 30,
    units: key === 'slope' ? 'degrees' : 'm above EGM2008', valid_pixels: 1, total_pixels: 2, missing_pixels: 1,
    retrieved_at: '2026-10-03T00:00:00Z', legend: key === 'land_cover' ? [{ value: 50, label: 'Built-up', color: '#fa0000' }] : { min: 1, max: 5, colors: ['#fff','#225d55'] },
  }])),
  mapped_drains: { type: 'FeatureCollection', features: [] },
  osm: { feature_count: 0, status: 'no_mapped_features', osm_base_timestamp: '2026-10-02T00:00:00Z', retrieved_at: '2026-10-03T00:00:00Z' },
  dem_quality: { EDM: { '1.0': 1 } }, height_error_m: { missing_pixels: 1 },
  sources: { [DEM]: { attribution: 'controlled Copernicus attribution', liability_notice: 'controlled liability notice', url: 'https://example.invalid/dem', license: 'Copernicus licence', license_url: 'https://example.invalid/license' },
    [LAND]: { attribution: 'controlled ESA attribution', url: 'https://example.invalid/land', license: 'CC BY 4.0', license_url: 'https://creativecommons.org/licenses/by/4.0/' },
    OpenStreetMap: { attribution: '© OpenStreetMap contributors', license: 'ODbL 1.0', url: 'https://www.openstreetmap.org/copyright', license_url: 'https://opendatacommons.org/licenses/odbl/1-0/' } },
})
const response = body => Promise.resolve({ ok: true, json: async () => body })
beforeEach(() => {
  vi.clearAllMocks()
  leaflet.map.mockReturnValue({ fitBounds: vi.fn(), remove: vi.fn(), removeLayer: vi.fn() })
  const overlay = () => ({ addTo: vi.fn().mockReturnThis(), on: vi.fn().mockReturnThis(), getBounds: vi.fn().mockReturnValue({}) })
  leaflet.tileLayer.mockImplementation(overlay)
  leaflet.geoJSON.mockImplementation(overlay)
  leaflet.imageOverlay.mockImplementation(overlay)
  vi.stubGlobal('fetch', vi.fn(() => response(fixture())))
})
afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.useRealTimers() })
const open = () => fireEvent.click(screen.getByRole('button', { name: 'Show research layers' }))

it('keeps the optional view closed without a request', () => {
  render(<DrainageResearchLayers />)
  expect(screen.getByRole('heading', { name: 'Drainage Research Layers' })).toBeTruthy()
  expect(fetch).not.toHaveBeenCalled()
  expect(leaflet.map).not.toHaveBeenCalled()
})

it('draws georeferenced rasters, source legends and unknown infrastructure coverage', async () => {
  render(<DrainageResearchLayers />); open()
  await screen.findByRole('region', { name: 'Udupi drainage research geography' })
  await waitFor(() => expect(leaflet.imageOverlay.mock.calls[0]?.slice(0,2)).toEqual(['/api/drainage-research/layers/elevation.png', [[13.33,74.73],[13.35,74.76]]]))
  expect(screen.getByText(/not an official municipal boundary/)).toBeTruthy()
  expect(screen.getByText(/does not mean there are no drains/)).toBeTruthy()
  expect(screen.getByLabelText(/Mapped drains and ditches/).disabled).toBe(true)
  expect(screen.getByRole('link', { name: 'ODbL 1.0' })).toBeTruthy()
  expect(screen.getByText(/controlled liability notice/)).toBeTruthy()
  expect(screen.getByText(/Transparent pixels are unknown/)).toBeTruthy()
})

it('switches raster layers with the correct categorical legend and preserves their meaning', async () => {
  render(<DrainageResearchLayers />); open()
  await screen.findByRole('region', { name: 'Udupi drainage research geography' })
  fireEvent.click(screen.getByLabelText('Land cover (2021)'))
  expect(screen.getByText('Built-up (50)')).toBeTruthy()
  expect(screen.getByLabelText('Surface elevation').checked).toBe(false)
  expect(leaflet.imageOverlay.mock.results[2].value.addTo).toHaveBeenCalled()
  fireEvent.click(screen.getByLabelText('Surface slope'))
  expect(screen.getByLabelText('Land cover (2021)').checked).toBe(false)
  expect(screen.getByText('1.00 degrees')).toBeTruthy()
  fireEvent.click(screen.getByRole('button', { name: 'Hide research layers' }))
  expect(leaflet.map.mock.results[0].value.remove).toHaveBeenCalled()
})

it('uses original OSM way geometry when mapped infrastructure exists', async () => {
  const data = fixture()
  data.osm = { ...data.osm, feature_count: 1, drain_count: 1, ditch_count: 0, clipped_length_m: 12.5 }
  data.mapped_drains.features.push({ type: 'Feature', properties: { osm_id: 123, waterway: 'drain' }, geometry: { type: 'LineString', coordinates: [[74.74,13.34],[74.75,13.34]] } })
  vi.mocked(fetch).mockImplementation(() => response(data))
  render(<DrainageResearchLayers />); open()
  await screen.findByRole('region', { name: 'Udupi drainage research geography' })
  fireEvent.click(screen.getByLabelText('Mapped drains and ditches'))
  expect(leaflet.geoJSON.mock.calls[1][0]).toEqual(data.mapped_drains)
  expect(screen.getByText(/12.5 m of clipped mapped lines/)).toBeTruthy()
})

it('handles missing source pixels without defaulting to a raster', async () => {
  const data = fixture(); data.layers.elevation.status = 'unavailable'
  vi.mocked(fetch).mockImplementation(() => response(data))
  render(<DrainageResearchLayers />); open()
  await screen.findByRole('region', { name: 'Udupi drainage research geography' })
  const control = screen.getByLabelText(/Surface elevation/)
  expect(control.disabled).toBe(true); expect(control.checked).toBe(false)
  expect(leaflet.imageOverlay).toHaveBeenCalledTimes(2)
})

it('reports unavailable datasets and rejects incorrect identities', async () => {
  const data = fixture(); data.layers.land_cover.source_id = 'wrong-source'
  vi.mocked(fetch).mockImplementation(() => response(data))
  render(<DrainageResearchLayers />); open()
  expect((await screen.findByRole('alert')).textContent).toContain('inconsistent')
  expect(leaflet.map).not.toHaveBeenCalled()
})

it('reports a strict request timeout and never substitutes data', async () => {
  vi.useFakeTimers()
  vi.mocked(fetch).mockImplementation((url, options) => new Promise((resolve, reject) => {
    options.signal.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError')))
  }))
  render(<DrainageResearchLayers />); open()
  await act(async () => { await vi.advanceTimersByTimeAsync(15000) })
  expect(screen.getByRole('alert').textContent).toContain('timed out')
  expect(leaflet.map).not.toHaveBeenCalled()
})
