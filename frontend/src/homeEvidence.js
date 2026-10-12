// Home summaries never prorate calendar-day rainfall into an hourly forecast.
const HOUR = 3600000
const DAY = 24 * HOUR
export function clock(value) {
  const time = typeof value === 'number' ? value : Date.parse(value)
  return Number.isFinite(time) ? new Intl.DateTimeFormat('en-IN', { dateStyle: 'medium', timeStyle: 'short', timeZone: 'Asia/Kolkata' }).format(time) + ' IST' : 'Time unavailable'
}
function timestamp(value) {
  return typeof value === 'string' && /(?:Z|[+-]\d\d:\d\d)$/.test(value) ? Date.parse(value) : NaN
}
export function rainfallWindow(intervals, start, end) {
  if (!Number.isFinite(start) || end - start !== DAY || !Array.isArray(intervals)) return null
  const rows = intervals.map(r => ({ start: timestamp(r.start), end: timestamp(r.end), mm: r.precipitation_mm, unit: r.unit }))
  // Invalid clocks cannot safely be excluded as outside this window.
  if (rows.some(r => !Number.isFinite(r.start) || !Number.isFinite(r.end) || r.end <= r.start)) return null
  const relevant = rows.filter(r => r.start < end && r.end > start).sort((a, b) => a.start - b.start)
  let cursor = start, total = 0
  for (const r of relevant) {
    if (r.start !== cursor || r.end > end || r.unit !== 'mm' || !Number.isFinite(r.mm) || r.mm < 0) return null
    total += r.mm; cursor = r.end
  }
  return cursor === end ? { mm: total, start, end } : null
}
export function next24Rainfall(data, now) {
  // Start at the next complete IST forecast hour; explicitly display both ends.
  const offset = 5.5 * HOUR
  const start = Math.ceil((now + offset) / HOUR) * HOUR - offset
  if (data?.forecast_coverage?.day_definition !== 'local_calendar_day' || data.forecast_coverage.timezone !== 'Asia/Kolkata' || data.forecast_units?.precipitation_mm !== 'mm') return null
  const intervals = data.forecast.map(d => ({ start: d.date + 'T00:00:00+05:30', end: new Date(Date.parse(d.date + 'T00:00:00+05:30') + DAY).toISOString(), precipitation_mm: d.precipitation_mm, unit: 'mm' }))
  return rainfallWindow(intervals, start, start + DAY)
}
export function usableCurrent(data, freshness, now) {
  const current = data?.current, valid = timestamp(current?.valid_at)
  return freshness === 'fresh' && current?.stale !== true && Number.isFinite(current?.temperature_c) && Number.isFinite(valid) && valid <= now && now - valid <= 90 * 60000 ? current : null
}
export function validHistoricalFeature(f) {
  const p = f?.properties, g = f?.geometry
  if (f?.type !== 'Feature' || p?.category !== 'historical_observed_floodwater' || p.geometry_crs !== 'OGC:CRS84' || p.observation_quality !== 'qualified_source_mask_and_clear_views' || p.source?.license !== 'CC BY-NC 4.0' || !p.source_geometry_sha256?.match(/^[a-f0-9]{64}$/) || !p.feature_id || !/^\d{4}-\d{2}-\d{2}$/.test(p.start_date) || !/^\d{4}-\d{2}-\d{2}$/.test(p.end_date_inclusive) || p.end_date_inclusive < p.start_date) return false
  const polygons = g?.type === 'Polygon' ? [g.coordinates] : g?.type === 'MultiPolygon' ? g.coordinates : null
  return Array.isArray(polygons) && polygons.length > 0 && polygons.every(poly => Array.isArray(poly) && poly.length > 0 && poly.every(ring => Array.isArray(ring) && ring.length >= 4 && ring.every(v => Array.isArray(v) && v.length >= 2 && Number.isFinite(v[0]) && Math.abs(v[0]) <= 180 && Number.isFinite(v[1]) && Math.abs(v[1]) <= 90) && ring[0][0] === ring.at(-1)[0] && ring[0][1] === ring.at(-1)[1]))
}
