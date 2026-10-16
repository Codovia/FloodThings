import React from 'react'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import RiskAreaDashboard, { spotLabel } from './RiskAreaDashboard.jsx'
import { rankedSpots, validRiskArea } from './useRisk.js'

afterEach(cleanup)
const summary = (level, score, reasons = []) => ({ level, score, max_score: 8, partial: false, reasons })
const cell = (id, km, dir, flood, drainage, extra = {}) => ({ id, latitude: 13, longitude: 74.7, distance_km: km, direction: dir, place: null,
  flood, drainage, inputs: { rain_24h_mm: 70, rain_5d_mm: 30, peak_mmh: 12, elevation_m: 6, historical_flood: null, approved_reports: 0 }, ...extra })
const data = { status: 'available', experimental: true, official_warning: false, cell_size_degrees: 0.05, label: 'Experimental risk index — fixture.', cells: [
  cell('a', 0.4, null, summary('moderate', 3), summary('low', 1)),
  cell('b', 6.1, 'NE', summary('high', 5, ['Forecast rain, next 24 h']), summary('moderate', 2), { place: 'Fixture town' }),
  cell('c', 11, 'S', summary('low', 0), summary('high', 4)),
  cell('d', 12, 'W', summary('unavailable', null), summary('unavailable', null)),
] }
const point = { name: 'Test place', latitude: 13, longitude: 74.7, kind: 'gps', accuracy_m: 30 }
const props = over => ({ area: { data, loading: false, error: null, refresh: vi.fn() }, point, kind: 'flood', onKind: vi.fn(), onFocus: vi.fn(), ...over })

it('validates the area contract and ranks spots by score, excluding unavailable ones', () => {
  expect(validRiskArea(data)).toBe(true)
  expect(validRiskArea({ ...data, official_warning: true })).toBe(false)
  expect(rankedSpots(data.cells, 'flood').map(c => c.id)).toEqual(['b', 'a', 'c'])
  expect(rankedSpots(data.cells, 'drainage').map(c => c.id)).toEqual(['c', 'b', 'a'])
  expect(spotLabel(data.cells[1])).toBe('6.1 km NE · near Fixture town'); expect(spotLabel(data.cells[0])).toBe('Your location')
})

it('lists the riskiest flood spots, counts unavailable separately and focuses the map', () => {
  const p = props(); render(<RiskAreaDashboard {...p} />)
  const list = screen.getByRole('list', { name: 'Highest flood risk spots' })
  expect(list.textContent).toMatch(/6.1 km NE · near Fixture town.*Your location/)
  expect(list.textContent).not.toContain('11 km S')
  expect(screen.getByLabelText('Flood risk counts').textContent).toContain('Unavailable')
  fireEvent.click(screen.getByRole('button', { name: /Show 6.1 km NE · near Fixture town on the map: High flood risk/ }))
  expect(p.onFocus).toHaveBeenCalledWith(data.cells[1])
  fireEvent.click(screen.getByRole('button', { name: 'Drainage' })); expect(p.onKind).toHaveBeenCalledWith('drainage')
})

it('says when nothing is above low, and never ranks a network estimate', () => {
  const calm = { ...data, cells: [cell('a', 0.4, null, summary('low', 1), summary('low', 0))] }
  const { rerender } = render(<RiskAreaDashboard {...props({ area: { data: calm, loading: false, error: null, refresh: vi.fn() } })} />)
  expect(screen.getByText(/No spot around you is above Low flood risk/)).toBeTruthy()
  rerender(<RiskAreaDashboard {...props({ point: { ...point, kind: 'network' }, area: { data: null, loading: false, error: null, refresh: vi.fn() } })} />)
  expect(screen.getByText(/only a network estimate/)).toBeTruthy(); expect(screen.queryByRole('list')).toBeNull()
})

it('reports failure and partial results without substitute levels', () => {
  const { rerender } = render(<RiskAreaDashboard {...props({ area: { data: null, loading: false, error: 'Risk request timed out.', refresh: vi.fn() } })} />)
  expect(screen.getByText(/Area prediction unavailable: Risk request timed out/)).toBeTruthy()
  rerender(<RiskAreaDashboard {...props({ area: { data: { ...data, status: 'partial' }, loading: false, error: null, refresh: vi.fn() } })} />)
  expect(screen.getByText(/risk is unknown, not low/)).toBeTruthy()
})
