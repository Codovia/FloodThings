import { expect, it } from 'vitest'
import { inGeometry, placeCheck } from './FloodIntelligenceMap.jsx'

// TEST FIXTURES ONLY — invented squares, not real districts, risk cells or floods.
const square = (x, y, d) => [[x, y], [x + d, y], [x + d, y + d], [x, y + d], [x, y]]
const official = { districts: [{ district: 'TEST-A', status: 'available', days: [{ level: 'orange', warnings: ['Very heavy rain'] }], geometry: { type: 'Polygon', coordinates: [square(74, 13, 1), square(74.4, 13.4, 0.2)] } }] }
const risk = { cell_size_degrees: 0.25, cells: [{ latitude: 13.5, longitude: 74.5, level: 'moderate', rain_24h_mm: 40 }] }
const history = { geojson: { features: [{ geometry: { type: 'Polygon', coordinates: [square(74.51, 13.51, 0.01)] } }, { geometry: { type: 'Polygon', coordinates: [square(75.5, 14.5, 0.01)] } }] } }

it('finds the district polygon (respecting holes), the covering risk area and past floods within 5 km', () => {
  expect(inGeometry(74.2, 13.2, official.districts[0].geometry)).toBe(true)
  expect(inGeometry(74.5, 13.5, official.districts[0].geometry)).toBe(false)  // inside the hole
  expect(inGeometry(76, 15, official.districts[0].geometry)).toBe(false)
  const r = placeCheck({ latitude: 13.52, longitude: 74.52 }, { official, risk, history })
  expect(r.imd).toBeNull()  // the hole is outside the district
  expect(r.cell.level).toBe('moderate'); expect(r.near).toBe(1)
  const inside = placeCheck({ latitude: 13.2, longitude: 74.2 }, { official, risk, history })
  expect(inside.imd.district).toBe('TEST-A'); expect(inside.cell).toBeNull(); expect(inside.near).toBe(0)
})

it('reports unknown instead of inventing answers when data is missing', () => {
  expect(placeCheck(null, { official, risk, history })).toBeNull()
  const r = placeCheck({ latitude: 13.2, longitude: 74.2 }, { official: null, risk: null, history: null })
  expect(r).toEqual({ imd: null, cell: null, near: null })
})
