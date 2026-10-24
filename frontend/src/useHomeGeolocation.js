import { useEffect, useRef, useState } from 'react'
import { classifyCoverage } from './homeGeography.js'
export const GPS_TIMEOUT_MS = 10000
export const MAX_WEATHER_ACCURACY_M = 10000 // Approximate point weather policy, not geographic certification.
export const MAX_CITY_ACCURACY_M = 5000 // Names above this radius are not local identity evidence.
const ATTEMPT_FLAG = 'floodpulse-home-location-attempted'
// Coordinates stay in React memory. Only a non-location tab-session attempt flag is stored.
function markAttempted() { try { sessionStorage.setItem(ATTEMPT_FLAG, '1') } catch { /* Storage may be blocked; the in-memory guard still applies. */ } }
const CLIENT_SOURCE = { provider: 'BigDataCloud', url: 'https://www.bigdatacloud.com/free-api/free-reverse-geocode-to-city-api' }
async function clientName(gps, job) {
  const params = new URLSearchParams({ localityLanguage: 'en' })
  if (gps) { params.set('latitude', gps.latitude); params.set('longitude', gps.longitude) }
  const response = await fetch('https://api.bigdatacloud.net/data/reverse-geocode-client?' + params, { signal: job.controller.signal, credentials: 'omit', referrerPolicy: 'no-referrer' })
  if (!response.ok) throw Error('Place provider unavailable')
  const body = await response.json(), name = body.city || body.locality
  if (typeof name !== 'string' || !name.trim() || name.length > 160 || /[\x00-\x1f]/.test(name) || typeof body.countryCode !== 'string') throw Error('Invalid town label')
  if (gps && (!['coordinates','reverseGeocoding'].includes(body.lookupSource) || !['latitude','longitude'].every(k => Number.isFinite(body[k]) && Math.abs(body[k]-gps[k]) < .0001))) throw Error('Unexpected location source')
  if (!gps && (!['ipGeolocation','ip geolocation'].includes(body.lookupSource) || !Number.isFinite(body.latitude) || Math.abs(body.latitude)>90 || !Number.isFinite(body.longitude) || Math.abs(body.longitude)>180)) throw Error('Invalid network estimate')
  return { ...(gps || { latitude: body.latitude, longitude: body.longitude, kind: 'network', accuracy_m: null }), name: name.trim(), name_source: CLIENT_SOURCE, name_accuracy: 'approximate_provider_label', administrative_identity_status: 'unverified', country_code: body.countryCode }
}
export default function useHomeGeolocation(active, manualRevision, hasSelection, onSelect) {
  const initialized = useRef(false), pending = useRef(null), live = useRef(active), select = useRef(onSelect)
  live.current = active; select.current = onSelect
  const [state, setState] = useState({ status: 'idle', message: 'Choose a place or allow location access.', gps: null })
  function cancel() {
    if (pending.current) { clearTimeout(pending.current.timer); pending.current.controller?.abort(); pending.current = null }
    if (live.current) setState(s => ({ ...s, status: 'manual', gps: null, message: 'Place you selected. Location access is optional.' }))
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
    function networkFallback(message, status) {
      if (job.browserDone || pending.current !== job || !live.current || job.revision !== manualRevision.current) return
      job.browserDone = true
      clearTimeout(job.timer)
      setState({ status, gps: null, message: message + ' Checking a separate approximate network city estimate…' })
      job.timer = setTimeout(() => { job.controller.abort(); finish(message + ' Network estimate unavailable; select your town.', status) }, GPS_TIMEOUT_MS)
      void clientName(null, job).then(named => {
        if (pending.current !== job || !live.current || job.revision !== manualRevision.current) return
        finish(); setState({ status: 'network', gps: null, message: 'Approximate network city estimate · BigDataCloud · uncertainty unknown. Weather is for the estimated point. Confirm your town before navigation or reporting.' }); select.current(named)
      }).catch(() => { if (pending.current === job) finish(message + ' Network estimate unavailable; select your town.', status) })
    }
    job.timer = setTimeout(() => networkFallback('Location request timed out.', 'timeout'), GPS_TIMEOUT_MS)
    try {
      navigator.geolocation.getCurrentPosition(result => {
        if (job.browserDone || pending.current !== job || !live.current || job.revision !== manualRevision.current) return
        const c = result?.coords, accuracy = c?.accuracy
        if (!Number.isFinite(c?.latitude) || Math.abs(c.latitude) > 90 || !Number.isFinite(c?.longitude) || Math.abs(c.longitude) > 180 || !Number.isFinite(accuracy) || accuracy < 0 || !Number.isFinite(result.timestamp) || result.timestamp > Date.now() + 1000 || Date.now() - result.timestamp > 60000) { finish('The returned location or its accuracy could not be verified. Search for a place instead.', 'invalid'); return }
        if (accuracy > MAX_WEATHER_ACCURACY_M) {
          networkFallback(`Approximate location — select your town. Browser-reported accuracy: ±${Math.round(accuracy)} m; this browser fix is not used.`, 'coarse')
          return
        }
        const gps = { name: 'GPS-selected point', latitude: c.latitude, longitude: c.longitude, accuracy_m: accuracy, gps_timestamp: result.timestamp, kind: 'gps' }
        const coverage = classifyCoverage(gps)
        if (pending.current !== job || !live.current || job.revision !== manualRevision.current) return
        clearTimeout(job.timer)
        const message = coverage === 'outside' ? 'Your location is outside Karnataka. Point weather only; map coverage is limited.' : coverage === 'uncertain' || coverage === 'unknown' ? 'Karnataka border coverage is uncertain; district unverified.' : 'Using your browser weather point; district unverified.'
        setState({ status: coverage, message: message + ` Browser-reported accuracy: ±${Math.round(accuracy)} m${accuracy > 100 ? '; approximate point weather' : ''}.`, gps })
        select.current(gps)
        job.timer = setTimeout(() => { job.controller.abort(); finish('Your GPS point is accepted. Place naming timed out; select your town to show a reviewed name.', coverage) }, GPS_TIMEOUT_MS)
        void (async () => { try {
          // Discover configured server provider without transmitting coordinates first.
          const config = await fetch('/api/location/provider', { signal: job.controller.signal }).then(r => r.ok ? r.json() : null).catch(() => null)
          if (pending.current !== job || job.controller.signal.aborted || job.revision !== manualRevision.current) return
          if (config?.provider !== 'MapTiler') {
            if (accuracy > MAX_CITY_ACCURACY_M) { finish('Approximate weather point accepted; accuracy cannot support a town label. Select your town.', coverage); return }
            const named = await clientName(gps, job)
            if (pending.current !== job || !live.current || job.revision !== manualRevision.current) return
            finish(); setState({ status: coverage, message: `Your device location (±${Math.round(accuracy)} m). Town name is approximate (BigDataCloud); district not verified.`, gps: named }); select.current(named); return
          }
          const response = await fetch('/api/location/reverse', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ latitude: gps.latitude, longitude: gps.longitude, accuracy_m: accuracy }), signal: job.controller.signal })
          const body = await response.json()
          if (pending.current !== job || !live.current || job.revision !== manualRevision.current || job.controller.signal.aborted) return
          if (response.ok && body.status === 'available' && body.accuracy_supported === true && body.geometry_verification === 'provider_locality_polygon_covers_accuracy' && body.source?.provider === 'MapTiler' && typeof body.name === 'string' && body.name.trim() && body.name.length <= 322) {
            const named = { ...gps, name: body.name, name_source: body.source, name_feature_id: body.feature_id, provider_context_label: body.context_label, administrative_identity_status: body.administrative_identity_status }
            finish(); setState({ status: coverage, message: `Your device location (±${Math.round(accuracy)} m). Place name is approximate; your district filter is unchanged.`, gps: named }); select.current(named)
          } else {
            finish(); setState({ status: coverage, message: `Your device location (±${Math.round(accuracy)} m). The place name is unavailable; search for your town to name it.` + (coverage === 'outside' ? ' Your location is outside Karnataka.' : coverage === 'uncertain' ? ' Border coverage uncertain.' : ''), gps })
          }
        } catch {
          if (pending.current === job && live.current && job.revision === manualRevision.current) {
            finish(); setState({ status: coverage, message: `Your device location (±${Math.round(accuracy)} m). The place name is unavailable; search for your town to name it.` + (coverage === 'outside' ? ' Your location is outside Karnataka.' : coverage === 'uncertain' ? ' Border coverage uncertain.' : ''), gps })
          }
        } })()
      }, error => networkFallback(error?.code === 1 ? 'Location permission was denied. Search for a place instead.' : error?.code === 3 ? 'Location request timed out. Search for a place or try again.' : 'Location could not be determined. Search for a place instead.', error?.code === 1 ? 'denied' : error?.code === 3 ? 'timeout' : 'unavailable'), { enableHighAccuracy: true, timeout: GPS_TIMEOUT_MS, maximumAge: 0 })
    } catch { finish('Location access is blocked by this browser. Search for a place instead.', 'unavailable') }
  }
  useEffect(() => {
    if (active && !initialized.current) { initialized.current = true; markAttempted(); if (!hasSelection) request() }
    return () => { if (pending.current) { clearTimeout(pending.current.timer); pending.current.controller?.abort(); pending.current = null; setState(s => ({ ...s, status: 'cancelled', message: 'Location request cancelled when leaving Home. Search for a place or choose Use my location.' })) } }
  }, [active]) // One automatic request during this App lifetime; explicit retries only.
  return { ...state, request, cancel }
}
