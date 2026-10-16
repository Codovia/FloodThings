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
      if (!response.ok && !data?.flood && !data?.cells) throw Error(typeof data?.detail === 'string' ? data.detail : 'Risk assessment unavailable')
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

export function useRiskPoint(point) {
  const ok = point && Number.isFinite(point.latitude) && Number.isFinite(point.longitude)
  const url = ok ? '/api/risk?' + new URLSearchParams({ latitude: point.latitude.toFixed(5), longitude: point.longitude.toFixed(5) }) : null
  return validated(useJson(url, 30 * 60 * 1000), validPointRisk)
}

export function useRiskGrid(active) {
  return validated(useJson(active ? '/api/risk/grid' : null, 30 * 60 * 1000), validRiskGrid)
}
