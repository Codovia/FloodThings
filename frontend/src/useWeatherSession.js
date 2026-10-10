import { useEffect, useRef, useState } from 'react'
import { DEFAULT_POINT } from './WeatherLocationSelector.jsx'

export const FRESHNESS_MS = 6 * 60 * 60 * 1000
export const RETRY_DELAYS_MS = [30 * 60 * 1000, 60 * 60 * 1000]
const REQUEST_TIMEOUT_MS = 15000
const keyOf = point => `${point.latitude}:${point.longitude}`

// Missing, timezone-less or future clocks cannot establish freshness. Never
// substitute a browser receipt for the backend's successful retrieval clock.
export function retrievalTime(value, now) {
  if (typeof value !== 'string' || !/^\d{4}-\d{2}-\d{2}T.*(?:Z|[+-]\d{2}:\d{2})$/.test(value)) return null
  const time = Date.parse(value)
  return Number.isFinite(time) && time <= now ? time : null
}
export function freshnessOf(data, loading, error, now) {
  if (loading) return 'refreshing'
  if (!data) return 'unavailable'
  const time = retrievalTime(data.retrieved_at, now)
  return error || time === null || now - time >= FRESHNESS_MS ? 'stale' : 'fresh'
}

export default function useWeatherSession(selectedPoint, enabled = true) {
  const point = selectedPoint || DEFAULT_POINT
  const key = keyOf(point)
  const session = useRef(null)
  const [view, setView] = useState({ key, data: null, loading: true, error: null, now: Date.now(), retryAt: null, paused: false, offline: false })
  const refresh = useRef(() => {})

  useEffect(() => {
    if (!enabled) return
    // One session per exact coordinate pair. Render-only changes to a location
    // name cannot schedule another request. A new location discards old data.
    const state = { key, data: null, error: null, active: null, timer: null, failures: 0, nextAt: null, stopped: false, offline: navigator.onLine === false }
    session.current = state
    function publish() {
      if (!state.stopped) setView({ key, data: state.data, loading: !!state.active, error: state.error, now: Date.now(), retryAt: state.failures ? state.nextAt : null, paused: state.failures >= 3, offline: state.offline })
    }
    function clearSchedule() { clearTimeout(state.timer); state.timer = null }
    function schedule() {
      clearSchedule()
      publish()
      if (state.stopped || state.active || document.hidden) return
      const validAt = Date.parse(state.data?.current?.valid_at)
      const validExpiry = validAt + 90 * 60 * 1000 + 1
      const clocks = [state.nextAt, validExpiry].filter(time => Number.isFinite(time) && time > Date.now())
      if (state.offline || state.nextAt === null) {
        const time = retrievalTime(state.data?.retrieved_at, Date.now())
        const expiries = [time === null ? null : time + FRESHNESS_MS, validExpiry].filter(time => Number.isFinite(time) && time > Date.now())
        if (expiries.length) state.timer = setTimeout(check, Math.min(...expiries) - Date.now())
        return
      }
      const wakeAt = state.nextAt <= Date.now() ? Date.now() : Math.min(...clocks)
      state.timer = setTimeout(check, Math.max(0, Math.min(wakeAt - Date.now(), FRESHNESS_MS)))
    }
    function check() {
      state.offline = navigator.onLine === false
      if (!state.stopped && !document.hidden && !state.offline && !state.active && state.nextAt !== null && Date.now() >= state.nextAt) void load(false)
      else schedule()
    }
    async function load(manual, overridePoint) {
      if (state.stopped || state.active) return // Never overlap same-location requests.
      clearSchedule()
      if (manual) state.failures = 0
      state.offline = navigator.onLine === false
      if (state.offline) {
        if (state.nextAt === null && state.failures < 3) state.nextAt = Date.now()
        state.error = 'Browser is offline. Previously retrieved information may be stale; reconnect or refresh manually.'
        publish(); return
      }
      const controller = new AbortController()
      const request = { controller, timeout: null }
      state.active = request
      state.error = null
      publish()
      request.timeout = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS)
      try {
        const requested = overridePoint || selectedPoint
        const query = requested ? '?' + new URLSearchParams({ latitude: requested.latitude, longitude: requested.longitude }) : ''
        const response = await fetch('/api/weather' + query, { signal: controller.signal })
        const body = await response.json()
        if (!response.ok || !['available', 'partial'].includes(body.status)) throw new Error(body.message || (typeof body.detail === 'string' ? body.detail : 'Weather is unavailable. Try again later.'))
        if (!body.current || !Array.isArray(body.forecast) || body.forecast.length > 7 ||
            body.forecast.some((day, i) => !/^\d{4}-\d{2}-\d{2}$/.test(day.date) || !Number.isFinite(Date.parse(day.date + 'T00:00:00+05:30')) || (i > 0 && day.date <= body.forecast[i - 1].date)) || !body.grid_location ||
            (requested && (body.location?.latitude !== requested.latitude || body.location?.longitude !== requested.longitude))) throw new Error('Weather response does not match the selected location.')
        if (state.stopped || state.active !== request || controller.signal.aborted) return
        state.data = body
        state.failures = 0
        const time = retrievalTime(body.retrieved_at, Date.now())
        // Unknown retrieval age stays stale. Delay the next attempt to avoid a
        // successful-but-clockless response causing an immediate request loop.
        state.nextAt = time === null ? Date.now() + FRESHNESS_MS : time + FRESHNESS_MS
        // An old backend response also gets a bounded cooldown, never a loop.
        if (state.nextAt <= Date.now()) state.nextAt = Date.now() + RETRY_DELAYS_MS[0]
      } catch (err) {
        if (state.stopped || state.active !== request) return
        state.error = err.name === 'AbortError' ? 'Weather request timed out. Try again.' : err.message
        state.failures++
        state.nextAt = state.failures < 3 ? Date.now() + RETRY_DELAYS_MS[state.failures - 1] : null
      } finally {
        clearTimeout(request.timeout)
        if (!state.stopped && state.active === request) { state.active = null; schedule() }
      }
    }
    const activate = () => check()
    const visibility = () => { if (document.hidden) schedule(); else check() }
    const offline = () => { state.offline = true; schedule() }
    document.addEventListener('visibilitychange', visibility)
    window.addEventListener('focus', activate)
    window.addEventListener('online', activate)
    window.addEventListener('offline', offline)
    refresh.current = override => load(true, override)
    void load(false)
    return () => {
      state.stopped = true
      clearSchedule()
      if (state.active) { clearTimeout(state.active.timeout); state.active.controller.abort() }
      document.removeEventListener('visibilitychange', visibility)
      window.removeEventListener('focus', activate)
      window.removeEventListener('online', activate)
      window.removeEventListener('offline', offline)
      if (session.current === state) { session.current = null; refresh.current = () => {} }
    }
  }, [key, enabled])

  // Do not render another location's response even before effect cleanup runs.
  const current = view.key === key ? view : { data: null, loading: true, error: null, now: Date.now(), retryAt: null, paused: false, offline: false }
  return { ...current, freshness: freshnessOf(current.data, current.loading, current.error, current.now), refresh: point => refresh.current(point) }
}
