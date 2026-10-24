import { useEffect, useState } from 'react'

export const LEVEL_COLORS = { low: '#2e7d32', moderate: '#f2a900', high: '#e65100', severe: '#b71c1c', unavailable: '#8a8f98' }
export const LEVEL_NAMES = { low: 'Low', moderate: 'Moderate', high: 'High', severe: 'Severe', unavailable: 'Unavailable' }

function useJson(url, refreshMs) {
  const [state, setState] = useState({ url: null, data: null, error: null, loading: false })
  const [tick, setTick] = useState(0)
  useEffect(() => {
    if (!url) return
    const controller = new AbortController(); let active = true
    const timer = setTimeout(() => controller.abort(), 45000)
    setState(s => ({ url, data: s.url === url ? s.data : null, error: null, loading: true }))
    fetch(url, { signal: controller.signal }).then(async response => {
      const data = await response.json()
      if (!response.ok && !data?.flood && !data?.cells) throw Error(typeof data?.detail === 'string' ? data.detail : typeof data?.message === 'string' ? data.message : 'Risk assessment unavailable')
      if (active) setState({ url, data, error: null, loading: false })
    }).catch(error => { if (active) setState({ url, data: null, error: error.name === 'AbortError' ? 'Risk request timed out.' : error.message, loading: false }) })
      .finally(() => clearTimeout(timer))
    const refresh = refreshMs && setTimeout(() => setTick(n => n + 1), refreshMs)
    return () => { active = false; clearTimeout(timer); clearTimeout(refresh); controller.abort() }
  }, [url, tick, refreshMs])
  if (!url) return { data: null, error: null, loading: false, refresh: () => {} }
  return { ...(state.url === url ? state : { data: null, error: null, loading: true }), refresh: () => setTick(n => n + 1) }
}

const LEVELS = new Set(Object.keys(LEVEL_NAMES))
const validResult = r => r && LEVELS.has(r.level) && Array.isArray(r.factors)
export const validPointRisk = d => !!d && d.experimental === true && validResult(d.flood) && validResult(d.drainage)
export const validRiskGrid = d => !!d && d.experimental === true && Array.isArray(d.cells) && Number.isFinite(d.cell_size_degrees) &&
  d.cells.every(c => Number.isFinite(c.latitude) && Number.isFinite(c.longitude) && LEVELS.has(c.level))

function validated(result, check) {
  if (!result.data || check(result.data)) return result
  return { ...result, data: null, error: 'Risk response could not be validated' }
}

// GloFAS river flood forecast for the checked Karnataka river points (modelled flow, not observed levels).
export const validRiverForecast = d => !!d && d.status === 'available' && Array.isArray(d.points) && d.points.length > 0 &&
  d.points.every(p => LEVELS.has(p.level) && typeof p.river === 'string' && typeof p.place === 'string' && Number.isFinite(p.grid?.latitude) &&
    Number.isFinite(p.grid?.longitude) && Number.isFinite(p.peak?.share_above?.['2_year']) && Number.isFinite(p.peak?.share_above?.['5_year']))
export function useRiverForecast(active) {
  return validated(useJson(active ? '/api/river-forecast' : null, 60 * 60 * 1000), validRiverForecast)
}

export function useRiskPoint(point) {
  const ok = point && Number.isFinite(point.latitude) && Number.isFinite(point.longitude)
  const url = ok ? '/api/risk?' + new URLSearchParams({ latitude: point.latitude.toFixed(5), longitude: point.longitude.toFixed(5) }) : null
  return validated(useJson(url, 30 * 60 * 1000), validPointRisk)
}

export function useRiskGrid(active) {
  return validated(useJson(active ? '/api/risk/grid' : null, 30 * 60 * 1000), validRiskGrid)
}

const validSummary = s => s && LEVELS.has(s.level) && Array.isArray(s.reasons)
export const validRiskArea = d => !!d && d.experimental === true && d.official_warning === false && Array.isArray(d.cells) && Number.isFinite(d.cell_size_degrees) &&
  d.cells.every(c => Number.isFinite(c.latitude) && Number.isFinite(c.longitude) && Number.isFinite(c.distance_km) && validSummary(c.flood) && validSummary(c.drainage))

// Nearby screen around the chosen place. A network estimate is too uncertain to rank spots "around you".
export function useRiskArea(point) {
  const ok = point && point.kind !== 'network' && Number.isFinite(point.latitude) && Number.isFinite(point.longitude)
  const url = ok ? '/api/risk/area?' + new URLSearchParams({ latitude: point.latitude.toFixed(5), longitude: point.longitude.toFixed(5) }) : null
  return validated(useJson(url, 30 * 60 * 1000), validRiskArea)
}

export const RANK = { severe: 4, high: 3, moderate: 2, low: 1, unavailable: 0 }
export function rankedSpots(cells, kind) {
  return [...cells].filter(c => c[kind].level !== 'unavailable')
    .sort((a, b) => (b[kind].score ?? -1) - (a[kind].score ?? -1) || a.distance_km - b.distance_km)
}

const OFFICIAL_LEVELS = new Set(['red', 'orange', 'yellow', 'green', null])
export const validOfficial = d => !!d && d.official === true && d.imd && d.sachet && Array.isArray(d.sachet.alerts) &&
  (d.imd.status !== 'available' || (Array.isArray(d.imd.days) && d.imd.days.every(x => OFFICIAL_LEVELS.has(x.level) && Array.isArray(x.warnings))))

// Official IMD / NDMA SACHET warnings, displayed as issued. Statewide alerts load even without a place.
export function useOfficialWarnings(point, active = true) {
  const ok = point && Number.isFinite(point.latitude) && Number.isFinite(point.longitude)
  const url = !active ? null : '/api/official/warnings' + (ok ? '?' + new URLSearchParams({ latitude: point.latitude.toFixed(5), longitude: point.longitude.toFixed(5) }) : '')
  return validated(useJson(url, 10 * 60 * 1000), validOfficial)
}

export const validOfficialDistricts = d => !!d && d.official === true && Array.isArray(d.districts) &&
  d.districts.every(x => typeof x.district === 'string' && x.geometry && Array.isArray(x.days) && x.days.every(day => OFFICIAL_LEVELS.has(day.level)))
export function useOfficialDistricts(active) {
  return validated(useJson(active ? '/api/official/districts' : null, 10 * 60 * 1000), validOfficialDistricts)
}
