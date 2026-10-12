import { describe, expect, it } from 'vitest'
import { rainfallWindow, next24Rainfall, usableCurrent, validHistoricalFeature } from './homeEvidence.js'
import { classifyCoverage, boundary } from './homeGeography.js'
import receipt from './data/karnatakaHomeBoundary.source.json'
import { createHash } from 'node:crypto'
import { readFileSync } from 'node:fs'
const start = Date.parse('2026-10-12T10:00:00+05:30')
const rows = Array.from({ length: 24 }, (_, i) => ({ start: new Date(start + i * 3600000).toISOString(), end: new Date(start + (i + 1) * 3600000).toISOString(), precipitation_mm: i / 10, unit: 'mm' }))
const copy = () => structuredClone(rows)
describe('strict 24-hour totals over whole supported intervals', () => {
  it('sums exactly 24 complete intervals in millimetres with offset-independent times', () => { expect(rainfallWindow(rows, start, start + 86400000).mm).toBeCloseTo(27.6) })
  it.each(['missing', 'duplicate', 'overlap', 'null', 'unit', 'negative', 'clock'])('rejects %s instead of inventing a total', kind => {
    const r = copy()
    if (kind === 'missing') r.splice(5, 1)
    if (kind === 'duplicate') r.push(r[5])
    if (kind === 'overlap') r[5].end = r[6].end
    if (kind === 'null') r[5].precipitation_mm = null
    if (kind === 'unit') r[5].unit = 'inches'
    if (kind === 'negative') r[5].precipitation_mm = -1
    if (kind === 'clock') r[5].start = '2026-10-12T10:00:00'
    expect(rainfallWindow(r, start, start + 86400000)).toBeNull()
  })
  it('never prorates daily totals; accepts only an exact midnight-aligned future window', () => {
    const data = { forecast_coverage: { day_definition: 'local_calendar_day', timezone: 'Asia/Kolkata' }, forecast_units: { precipitation_mm: 'mm' }, forecast: [{ date: '2026-10-13', precipitation_mm: 12 }] }
    expect(next24Rainfall(data, start)).toBeNull()
    const midnight = Date.parse('2026-10-13T00:00:00+05:30')
    expect(next24Rainfall(data, midnight - 1800000)).toEqual({ start: midnight, end: midnight + 86400000, mm: 12 })
    expect(next24Rainfall({ ...data, forecast_units: {} }, midnight)).toBeNull()
    expect(next24Rainfall({ ...data, forecast: [{ date: '2026-10-13', precipitation_mm: null }] }, midnight)).toBeNull()
  })
})
it('current model estimate requires valid fresh timestamps and a finite temperature', () => {
  const data = { current: { valid_at: new Date(start).toISOString(), temperature_c: 27 } }
  expect(usableCurrent(data, 'fresh', start)).toBe(data.current)
  expect(usableCurrent(data, 'stale', start)).toBeNull()
  expect(usableCurrent(data, 'fresh', start + 91 * 60000)).toBeNull()
  expect(usableCurrent(data, 'fresh', start - 1)).toBeNull()
  expect(usableCurrent({ current: { ...data.current, temperature_c: null } }, 'fresh', start)).toBeNull()
})
it('retains only attributed, observation-qualified historical polygon cells', () => {
  const f = { type: 'Feature', geometry: { type: 'Polygon', coordinates: [[[74,13],[75,13],[75,14],[74,13]]] }, properties: { feature_id: 'gfd:1', category: 'historical_observed_floodwater', geometry_crs: 'OGC:CRS84', observation_quality: 'qualified_source_mask_and_clear_views', source: { license: 'CC BY-NC 4.0' }, source_geometry_sha256: 'a'.repeat(64), start_date: '2021-07-01', end_date_inclusive: '2021-07-02' } }
  expect(validHistoricalFeature(f)).toBe(true)
  expect(validHistoricalFeature({ ...f, properties: { ...f.properties, category: 'predicted_flood' } })).toBe(false)
  expect(validHistoricalFeature({ ...f, geometry: { type: 'Point', coordinates: [74,13] } })).toBe(false)
  const invalid = structuredClone(f); invalid.geometry.coordinates[0][0][0] = 999
  expect(validHistoricalFeature(invalid)).toBe(false)
})
it('public Home state context matches the rights receipt and pinned feature identity', () => {
  const raw = readFileSync('src/data/karnatakaHomeBoundary.json')
  expect(raw.length).toBe(receipt.derived_bytes)
  expect(createHash('sha256').update(raw).digest('hex')).toBe(receipt.derived_sha256)
  expect(boundary.properties.shapeISO).toBe('IN-KA')
  expect(receipt.license).toContain('CC BY 2.5 IN')
})
it('screens actual Karnataka geography, including Goa rather than just a bounding box', () => {
  expect(classifyCoverage({ latitude: 12.97, longitude: 77.59 })).toBe('inside')
  expect(classifyCoverage({ latitude: 28.61, longitude: 77.21 })).toBe('outside')
  expect(classifyCoverage({ latitude: 15.49, longitude: 73.83 })).toBe('outside')
  const vertex = boundary.geometry.coordinates[0][0]
  expect(classifyCoverage({ latitude: vertex[1], longitude: vertex[0], accuracy_m: 30 })).toBe('uncertain')
})
it('handles holes, large uncertainty and missing geography conservatively', () => {
  const geometry = { type: 'Polygon', coordinates: [[[0,0],[10,0],[10,10],[0,10],[0,0]], [[4,4],[6,4],[6,6],[4,6],[4,4]]] }
  expect(classifyCoverage({ latitude:5, longitude:5 }, geometry)).toBe('outside')
  expect(classifyCoverage({ latitude:3, longitude:3, accuracy_m:500000 }, geometry)).toBe('uncertain')
  expect(classifyCoverage({ latitude:NaN, longitude:0 }, geometry)).toBe('unknown')
  expect(classifyCoverage({ latitude:5, longitude:5 }, null)).toBe('unknown')
})
