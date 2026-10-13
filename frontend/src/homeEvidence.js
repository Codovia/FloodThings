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
  if (intervals.some(r => !r || typeof r !== 'object')) return null
  const rows = intervals.map(r => ({ start: timestamp(r.start), end: timestamp(r.end), mm: r.precipitation_mm, unit: r.unit }))
  // Invalid clocks cannot safely be excluded as outside this window.
  if (rows.some(r => !Number.isFinite(r.start) || !Number.isFinite(r.end) || r.end <= r.start)) return null
  if (rows.some((r, i) => r.end - r.start !== HOUR || (i > 0 && r.end <= rows[i - 1].end))) return null
  const relevant = rows.filter(r => r.start < end && r.end > start)
  if (relevant.length !== 24) return null
  let cursor = start, total = 0
  for (const r of relevant) {
    if (r.start !== cursor || r.end > end || r.unit !== 'mm' || !Number.isFinite(r.mm) || r.mm < 0) return null
    total += r.mm; cursor = r.end
  }
  return cursor === end && Number.isFinite(total) ? { mm: total, start, end } : null
}
export function assessNext24Rainfall(data, now) {
  // Provider timestamps END the preceding hour: first selected end is start + 1h.
  const offset = 5.5 * HOUR
  const start = Math.ceil((now + offset) / HOUR) * HOUR - offset
  const hourly = data?.hourly_precipitation
  const unavailable = reason => ({ status: 'unavailable', reason, start, end: start + DAY, interval_count: 0, mm: null })
  if (!Number.isFinite(now)) return unavailable('Reference time is invalid.')
  if (!hourly || hourly.status !== 'available') return unavailable(hourly?.message || 'Hourly precipitation was not supplied; calendar-day totals cannot substitute.')
  if (hourly.timezone !== 'Asia/Kolkata' || hourly.unit !== 'mm' || hourly.interval_seconds !== 3600 || hourly.interval_semantics !== 'preceding_hour') return unavailable('Hourly units or preceding-hour timestamp semantics are invalid.')
  const result = rainfallWindow(hourly.intervals, start, start + DAY)
  return result ? { ...result, status: 'available', interval_count: 24, source: hourly.source, retrieved_at: data.retrieved_at, forecast_issued_at: data.forecast_issued_at ?? null } : unavailable('Exactly 24 ordered, consecutive one-hour intervals with valid millimetre values are required; timestamps or values are missing or invalid.')
}
export function next24Rainfall(data, now) {
  const result = assessNext24Rainfall(data, now)
  return result.status === 'available' ? result : null
}
export function usableCurrent(data, freshness, now) {
  const current = data?.current, valid = timestamp(current?.valid_at)
  const hasValue = ['temperature_c', 'humidity_percent', 'precipitation_mm', 'weather_code', 'wind_speed'].some(field => Number.isFinite(current?.[field]))
  return freshness === 'fresh' && current?.stale !== true && hasValue && Number.isFinite(valid) && valid <= now && now - valid <= 90 * 60000 ? current : null
}
export function validHistoricalFeature(f) {
  const p = f?.properties, g = f?.geometry
  if (f?.type !== 'Feature' || p?.category !== 'historical_observed_floodwater' || p.geometry_crs !== 'OGC:CRS84' || p.observation_quality !== 'qualified_source_mask_and_clear_views' || p.source?.license !== 'CC BY-NC 4.0' || !p.source_geometry_sha256?.match(/^[a-f0-9]{64}$/) || !p.feature_id || !/^\d{4}-\d{2}-\d{2}$/.test(p.start_date) || !/^\d{4}-\d{2}-\d{2}$/.test(p.end_date_inclusive) || p.end_date_inclusive < p.start_date) return false
  const polygons = g?.type === 'Polygon' ? [g.coordinates] : g?.type === 'MultiPolygon' ? g.coordinates : null
  return Array.isArray(polygons) && polygons.length > 0 && polygons.every(poly => Array.isArray(poly) && poly.length > 0 && poly.every(ring => Array.isArray(ring) && ring.length >= 4 && ring.every(v => Array.isArray(v) && v.length >= 2 && Number.isFinite(v[0]) && Math.abs(v[0]) <= 180 && Number.isFinite(v[1]) && Math.abs(v[1]) <= 90) && ring[0][0] === ring.at(-1)[0] && ring[0][1] === ring.at(-1)[1]))
}
