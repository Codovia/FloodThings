import { useEffect, useRef, useState } from 'react'

// Availability is administrator-reported, never an occupancy guarantee. A
// successful directory check is usable for at most one minute in an active tab.
export const SHELTER_FRESHNESS_MS = 60000
export const SHELTER_FAILURE_COOLDOWN_MS = 30000
export function validShelterDirectory(data, now = Date.now()) {
  return ['live', 'demonstration'].includes(data?.mode) && Array.isArray(data.shelters) && data.shelters.every(s =>
    s.status === 'open' && s.available_capacity > 0 && Number.isFinite(s.latitude) && Math.abs(s.latitude) <= 90 &&
    Number.isFinite(s.longitude) && Math.abs(s.longitude) <= 180 && Number.isFinite(Date.parse(s.verified_at)) &&
    Date.parse(s.verification_expires_at) > now && s.demonstration === (data.mode === 'demonstration'))
}

export default function useShelterDirectory(point, active) {
  const query = point ? '?' + new URLSearchParams({ latitude: point.latitude, longitude: point.longitude }) : ''
  const url = '/api/shelters' + query
  const refresh = useRef(async () => null)
  const [view, setView] = useState({ url: null, data: null, loading: false, error: null, checkedAt: null })
  useEffect(() => {
    if (!active) return
    let stopped = false, timer = null, request = null, failedAt = null
    function clearTimer() { clearTimeout(timer); timer = null }
    function load(manual = false) {
      if (stopped) return Promise.resolve(null)
      if (request) return request.promise
      clearTimer()
      if (!manual && failedAt !== null && Date.now() - failedAt < SHELTER_FAILURE_COOLDOWN_MS) return Promise.resolve(null)
      const controller = new AbortController()
      const current = { controller, promise: null, timeout: null }
      let abortListener
      request = current
      setView({ url, data: null, loading: true, error: null, checkedAt: null })
      current.timeout = setTimeout(() => controller.abort(), 15000)
      current.promise = (async () => {
        try {
          const aborted = new Promise((_, reject) => {
            abortListener = () => reject(new DOMException('Aborted', 'AbortError'))
            controller.signal.addEventListener('abort', abortListener, { once: true })
          })
          const { response, data } = await Promise.race([
            (async () => { const response = await fetch(url, { signal: controller.signal, cache: 'no-store' }); return { response, data: await response.json() } })(),
            aborted,
          ])
          if (!response.ok) throw Error(typeof data.detail === 'string' ? data.detail : 'Shelter directory unavailable')
          if (data.status !== 'available' || !validShelterDirectory(data)) throw Error('Shelter availability could not be verified')
          if (stopped || controller.signal.aborted) return null
          failedAt = null
          const checkedAt = Date.now()
          setView({ url, data, loading: false, error: null, checkedAt })
          if (!document.hidden) {
            const expiresAt = Math.min(checkedAt + SHELTER_FRESHNESS_MS, ...data.shelters.map(s => Date.parse(s.verification_expires_at)))
            timer = setTimeout(() => load(), Math.max(0, expiresAt - Date.now()))
          }
          return data
        } catch (error) {
          if (!stopped) {
            failedAt = Date.now()
            setView({ url, data: null, loading: false, checkedAt: null, error: error.name === 'AbortError' ? 'Shelter directory request timed out. Please retry.' : error.message })
          }
          return null
        } finally {
          clearTimeout(current.timeout)
          controller.signal.removeEventListener('abort', abortListener)
          if (request === current) request = null
        }
      })()
      return current.promise
    }
    function activate() { if (!document.hidden) void load() }
    function visibility() { if (document.hidden) clearTimer(); else activate() }
    refresh.current = () => load(true)
    document.addEventListener('visibilitychange', visibility)
    window.addEventListener('focus', activate)
    window.addEventListener('online', activate)
    void load()
    return () => {
      stopped = true; clearTimer(); refresh.current = async () => null
      if (request) { clearTimeout(request.timeout); request.controller.abort() }
      document.removeEventListener('visibilitychange', visibility)
      window.removeEventListener('focus', activate)
      window.removeEventListener('online', activate)
    }
  }, [url, active])
  const current = active && view.url === url ? view : { data: null, loading: !!active, error: null, checkedAt: null }
  const fresh = current.data && Date.now() - current.checkedAt < SHELTER_FRESHNESS_MS && validShelterDirectory(current.data)
  return { ...current, data: fresh ? current.data : null, refresh: () => refresh.current(), freshness: current.loading ? 'refreshing' : fresh ? 'fresh' : 'unavailable' }
}
