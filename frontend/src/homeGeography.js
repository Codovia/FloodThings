import boundary from './data/karnatakaHomeBoundary.json'
export const KARNATAKA_CENTER = [15.1, 76.1]
export const COVERAGE_MARGIN_M = 2000 // Policy caution margin, not source positional accuracy.
function containsRing(lon, lat, ring) {
  let inside = false
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    const [xi, yi] = ring[i], [xj, yj] = ring[j]
    if ((yi > lat) !== (yj > lat) && lon < (xj - xi) * (lat - yi) / (yj - yi) + xi) inside = !inside
  }
  return inside
}
export function classifyCoverage(point, geometry = boundary.geometry) {
  const { latitude: lat, longitude: lon, accuracy_m: accuracy = 0 } = point || {}
  if (!Number.isFinite(lat) || Math.abs(lat) > 90 || !Number.isFinite(lon) || Math.abs(lon) > 180 || !Number.isFinite(accuracy) || accuracy < 0) return 'unknown'
  const polygons = geometry?.type === 'Polygon' ? [geometry.coordinates] : geometry?.type === 'MultiPolygon' ? geometry.coordinates : null
  if (!polygons?.length) return 'unknown'
  let distance = Infinity, inside = false
  const xscale = 111320 * Math.cos(lat * Math.PI / 180), yscale = 111320
  for (const polygon of polygons) {
    if (!polygon?.length || polygon.some(r => !Array.isArray(r) || r.length < 4 || r.some(v => !Number.isFinite(v?.[0]) || !Number.isFinite(v?.[1])))) return 'unknown'
    if (containsRing(lon, lat, polygon[0]) && !polygon.slice(1).some(r => containsRing(lon, lat, r))) inside = true
    for (const ring of polygon) for (let i = 1; i < ring.length; i++) {
      const a = [(ring[i - 1][0] - lon) * xscale, (ring[i - 1][1] - lat) * yscale], b = [(ring[i][0] - lon) * xscale, (ring[i][1] - lat) * yscale]
      const dx = b[0] - a[0], dy = b[1] - a[1], length = dx * dx + dy * dy
      const t = length ? Math.max(0, Math.min(1, -(a[0] * dx + a[1] * dy) / length)) : 0
      distance = Math.min(distance, Math.hypot(a[0] + t * dx, a[1] + t * dy))
    }
  }
  if (distance <= accuracy + COVERAGE_MARGIN_M) return 'uncertain'
  return inside ? 'inside' : 'outside'
}
export { boundary }
