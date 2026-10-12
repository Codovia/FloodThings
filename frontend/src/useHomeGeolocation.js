import { useEffect, useRef, useState } from 'react'
import { classifyCoverage } from './homeGeography.js'
export const GPS_TIMEOUT_MS = 10000
const ATTEMPT_FLAG = 'floodpulse-home-location-attempted'
// Coordinates stay in React memory. Only a non-location tab-session attempt flag is stored.
function previouslyAttempted() { try { return sessionStorage.getItem(ATTEMPT_FLAG) === '1' } catch { return false } }
function markAttempted() { try { sessionStorage.setItem(ATTEMPT_FLAG, '1') } catch { /* Storage may be blocked; the in-memory guard still applies. */ } }
export default function useHomeGeolocation(active, manualRevision, hasSelection, onSelect) {
  const initialized = useRef(false), pending = useRef(null), live = useRef(active), select = useRef(onSelect)
  live.current = active; select.current = onSelect
  const [state, setState] = useState({ status: 'idle', message: 'Choose a place or allow location access.', gps: null })
  function cancel() {
    if (pending.current) { clearTimeout(pending.current.timer); pending.current = null }
    if (live.current) setState(s => ({ ...s, status: 'manual', message: 'Using your selected place or district filter. Location access remains optional.' }))
  }
  function request() {
    if (!live.current || pending.current) return
    if (window.isSecureContext !== true) { setState(s => ({ ...s, status: 'insecure', message: 'Location requires a secure connection. Search for a place instead.' })); return }
    if (!navigator.geolocation?.getCurrentPosition) { setState(s => ({ ...s, status: 'unsupported', message: 'Location access is unavailable in this browser. Search for a place instead.' })); return }
    const job = { revision: manualRevision.current, timer: null }; pending.current = job
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
        const gps = { name: 'GPS-selected point', latitude: c.latitude, longitude: c.longitude, accuracy_m: accuracy, gps_timestamp: result.timestamp, kind: 'gps' }
        const coverage = classifyCoverage(gps)
        if (!finish()) return
        const message = coverage === 'outside' ? 'Your location is outside Karnataka. Point weather may be available; Karnataka flood evidence does not cover this location.' : coverage === 'uncertain' || coverage === 'unknown' ? 'Your location overlaps the state-boundary uncertainty area. Karnataka coverage and district association are unconfirmed.' : 'Using your GPS point. District association is unconfirmed.'
        setState({ status: coverage, message: message + ` Browser-reported accuracy: ±${Math.round(accuracy)} m.`, gps })
        select.current(gps)
      }, error => finish(error?.code === 1 ? 'Location permission was denied. Search for a place instead.' : error?.code === 3 ? 'Location request timed out. Search for a place or try again.' : 'Location could not be determined. Search for a place instead.', error?.code === 1 ? 'denied' : error?.code === 3 ? 'timeout' : 'unavailable'), { enableHighAccuracy: false, timeout: GPS_TIMEOUT_MS, maximumAge: 0 })
    } catch { finish('Location access is blocked by this browser. Search for a place instead.', 'unavailable') }
  }
  useEffect(() => {
    if (active && !initialized.current) { initialized.current = true; const attempted = previouslyAttempted(); markAttempted(); if (!hasSelection && !attempted) request() }
    return () => { if (pending.current) { clearTimeout(pending.current.timer); pending.current = null; setState(s => ({ ...s, status: 'cancelled', message: 'Location request cancelled when leaving Home. Search for a place or choose Use my location.' })) } }
  }, [active]) // One automatic request during this App lifetime; explicit retries only.
  return { ...state, request, cancel }
}
