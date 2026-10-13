import { useEffect, useRef, useState } from 'react'
import { classifyCoverage } from './homeGeography.js'
export const GPS_TIMEOUT_MS = 10000
export const MAX_GPS_ACCURACY_M = 100 // Acceptance policy; not a certified geographic accuracy.
const ATTEMPT_FLAG = 'floodpulse-home-location-attempted'
// Coordinates stay in React memory. Only a non-location tab-session attempt flag is stored.
function previouslyAttempted() { try { return sessionStorage.getItem(ATTEMPT_FLAG) === '1' } catch { return false } }
function markAttempted() { try { sessionStorage.setItem(ATTEMPT_FLAG, '1') } catch { /* Storage may be blocked; the in-memory guard still applies. */ } }
export default function useHomeGeolocation(active, manualRevision, hasSelection, onSelect) {
  const initialized = useRef(false), pending = useRef(null), live = useRef(active), select = useRef(onSelect)
  live.current = active; select.current = onSelect
  const [state, setState] = useState({ status: 'idle', message: 'Choose a place or allow location access.', gps: null })
  function cancel() {
    if (pending.current) { clearTimeout(pending.current.timer); pending.current.controller?.abort(); pending.current = null }
    if (live.current) setState(s => ({ ...s, status: 'manual', gps: null, message: 'Using your selected place or district filter. Location access remains optional.' }))
  }
  function request() {
    if (!live.current || pending.current) return
    if (window.isSecureContext !== true) { setState(s => ({ ...s, status: 'insecure', message: 'Location requires a secure connection. Search for a place instead.' })); return }
    if (!navigator.geolocation?.getCurrentPosition) { setState(s => ({ ...s, status: 'unsupported', message: 'Location access is unavailable in this browser. Search for a place instead.' })); return }
    const job = { revision: manualRevision.current, timer: null, controller: new AbortController() }; pending.current = job
    setState(s => ({ ...s, status: 'requesting', message: 'Waiting for location permission… You can also search for a place.' }))
    function finish(message, status) {
      if (pending.current !== job || !live.current || job.revision !== manualRevision.current) return false
      clearTimeout(job.timer); pending.current = null
      if (message) setState(s => ({ ...s, status, message }))
      return true
    }
    job.timer = setTimeout(() => finish('Location request timed out. Search for a place or try again.', 'timeout'), GPS_TIMEOUT_MS)
    try {
      navigator.geolocation.getCurrentPosition(result => {
        const c = result?.coords, accuracy = c?.accuracy
        if (!Number.isFinite(c?.latitude) || Math.abs(c.latitude) > 90 || !Number.isFinite(c?.longitude) || Math.abs(c.longitude) > 180 || !Number.isFinite(accuracy) || accuracy < 0 || !Number.isFinite(result.timestamp) || result.timestamp > Date.now() + 1000 || Date.now() - result.timestamp > 60000) { finish('The returned location or its accuracy could not be verified. Search for a place instead.', 'invalid'); return }
        if (accuracy > MAX_GPS_ACCURACY_M) {
          if (finish()) setState({ status: 'coarse', gps: null, message: `Approximate location — select your town. Browser-reported accuracy: ±${Math.round(accuracy)} m; local weather and river focus require a more precise point or manual selection.` })
          return
        }
        const gps = { name: 'GPS-selected point', latitude: c.latitude, longitude: c.longitude, accuracy_m: accuracy, gps_timestamp: result.timestamp, kind: 'gps' }
        const coverage = classifyCoverage(gps)
        if (pending.current !== job || !live.current || job.revision !== manualRevision.current) return
        clearTimeout(job.timer)
        const message = coverage === 'outside' ? 'Your location is outside Karnataka. Point weather only; map coverage is limited.' : coverage === 'uncertain' || coverage === 'unknown' ? 'Karnataka border coverage is uncertain; district unverified.' : 'Using your GPS weather point; district unverified.'
        setState({ status: coverage, message: message + ` Browser-reported accuracy: ±${Math.round(accuracy)} m.`, gps })
        select.current(gps)
        job.timer = setTimeout(() => { job.controller.abort(); finish('Your GPS point is accepted. Place naming timed out; select your town to show a reviewed name.', coverage) }, GPS_TIMEOUT_MS)
        void (async () => { try {
          const response = await fetch('/api/location/reverse', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ latitude: gps.latitude, longitude: gps.longitude, accuracy_m: accuracy }), signal: job.controller.signal })
          const body = await response.json()
          if (pending.current !== job || !live.current || job.revision !== manualRevision.current || job.controller.signal.aborted) return
          if (response.ok && body.status === 'available' && body.accuracy_supported === true && body.geometry_verification === 'provider_locality_polygon_covers_accuracy' && body.source?.provider === 'MapTiler' && typeof body.name === 'string' && body.name.trim() && body.name.length <= 322) {
            const named = { ...gps, name: body.name, name_source: body.source, name_feature_id: body.feature_id, provider_context_label: body.context_label, administrative_identity_status: body.administrative_identity_status }
            finish(); setState({ status: coverage, message: `Provider place label · Browser-reported accuracy: ±${Math.round(accuracy)} m. District filter unchanged.`, gps: named }); select.current(named)
          } else {
            finish(); setState({ status: coverage, message: `Browser-reported accuracy: ±${Math.round(accuracy)} m. Place naming is unavailable; select your town.` + (coverage === 'outside' ? ' Your location is outside Karnataka.' : coverage === 'uncertain' ? ' Border coverage uncertain.' : ''), gps })
          }
        } catch {
          if (pending.current === job && live.current && job.revision === manualRevision.current) {
            finish(); setState({ status: coverage, message: `Browser-reported accuracy: ±${Math.round(accuracy)} m. Place naming is unavailable; select your town.` + (coverage === 'outside' ? ' Your location is outside Karnataka.' : coverage === 'uncertain' ? ' Border coverage uncertain.' : ''), gps })
          }
        } })()
      }, error => finish(error?.code === 1 ? 'Location permission was denied. Search for a place instead.' : error?.code === 3 ? 'Location request timed out. Search for a place or try again.' : 'Location could not be determined. Search for a place instead.', error?.code === 1 ? 'denied' : error?.code === 3 ? 'timeout' : 'unavailable'), { enableHighAccuracy: true, timeout: GPS_TIMEOUT_MS, maximumAge: 0 })
    } catch { finish('Location access is blocked by this browser. Search for a place instead.', 'unavailable') }
  }
  useEffect(() => {
    if (active && !initialized.current) { initialized.current = true; const attempted = previouslyAttempted(); markAttempted(); if (!hasSelection && !attempted) request() }
    return () => { if (pending.current) { clearTimeout(pending.current.timer); pending.current.controller?.abort(); pending.current = null; setState(s => ({ ...s, status: 'cancelled', message: 'Location request cancelled when leaving Home. Search for a place or choose Use my location.' })) } }
  }, [active]) // One automatic request during this App lifetime; explicit retries only.
  return { ...state, request, cancel }
}
